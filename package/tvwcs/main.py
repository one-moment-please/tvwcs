#!/usr/bin/env python3
"""TVWCS — Metro-style TV launcher and workspace switcher for i3 and sway. Application controller and command line."""
from __future__ import annotations
import os, shlex, signal, subprocess, sys
from pathlib import Path
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from tvwcs.applications import ApplicationCatalogue, match_window
from tvwcs.hotkeys import MODIFIER_KEYSYMS, render_i3
from tvwcs.model import CONFIG_HOME, LAUNCH_NEW_WORKSPACE, LAUNCH_SAME, PIN_LAUNCH_AND_SHOW, SCALE_PRESETS, ConfigStore, compute_layout, is_4k
from tvwcs.ownership import WindowOwners
from tvwcs.pinlock import PinGate
from tvwcs import privilege
from tvwcs.session import first_time_this_login, is_tvwcs_process, runtime_dir
from tvwcs.system_actions import POWER_VERBS, SYSTEM_ACTIONS, command_for, unavailable_message
from tvwcs.ui_editors import ApplicationProfilesWindow, ProfileEditor
from tvwcs.ui_window import TVWCSWindow
from tvwcs.widgets import app_icon, has_icon, set_scale
from tvwcs.window_manager import I3WindowManager
from tvwcs.workspaces import build_entries

APP_ID="com.tvwcs.TVWCS"
RUNTIME=runtime_dir()                            # XDG_RUNTIME_DIR, or ~/.cache/tvwcs without one (see session.py)
PID_FILE=RUNTIME/"tvwcs.pid"
STARTUP_MARKER=RUNTIME/"tvwcs-startup-done"      # records the login the start-up action last ran in
PASSWORD_TRIES=3                                  # wrong administrator passwords before TVWCS gives up
STARTUP_MENU_DELAY=2500                           # ms between opening the login app and showing the Quick Menu over it
REQUESTS_FILE=RUNTIME/"tvwcs-requests"          # `tvwcs launch <id>` appends a line here, then signals the running TVWCS
HOTKEYS_FILE=CONFIG_HOME/"tvwcs"/"hotkeys.conf"  # generated from Settings; included by tvwcs.conf
def _find_launcher():
    """Locate the tvwcs launcher script next to the package (works in the repo layout, the
    install.sh layout ~/.local/share/tvwcs, and a zip extracted anywhere)."""
    here=Path(__file__).resolve().parent          # .../tvwcs (the package)
    for cand in (here.parent/"bin"/"tvwcs", here/"tvwcs", here.parent.parent/"bin"/"tvwcs"):
        if cand.exists(): return cand
    return here.parent/"bin"/"tvwcs"              # sensible default even if missing

LAUNCHER=_find_launcher()

class TVWCSApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.window=None; self.catalogue=ApplicationCatalogue(); self.store=ConfigStore(); self.wm=I3WindowManager()
        self.layout=None; self._owns_pid=False
        self.pin_gate=PinGate(); self.owners=WindowOwners()
        self._fullscreen=set()   # windows that were fullscreen when TVWCS was shown; they are made fullscreen again when it hides

    @property
    def scale_factor(self): return SCALE_PRESETS[self.store.settings["scale"]]

    # ---------------------------------------------------------- lifecycle
    def do_startup(self):
        Gtk.Application.do_startup(self)
        if not self._claim_pid(): GLib.idle_add(self.quit); return
        set_scale(self.scale_factor)
        # Keep the application alive while its only window is hidden; IPC arrives as Unix signals handled by the GLib loop.
        self.hold()
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGUSR1,lambda:(self.show_mode("toggle"),GLib.SOURCE_CONTINUE)[1])
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGUSR2,lambda:(self.show_mode("guide"),GLib.SOURCE_CONTINUE)[1])
        # Requests that carry an argument (an application hotkey) are queued in REQUESTS_FILE. SIGWINCH is harmless to
        # ignore and GLib can watch it; a stray one finds no queue and does nothing.
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGWINCH,lambda:(self._take_requests(),GLib.SOURCE_CONTINUE)[1])
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGTERM,self._on_stop_signal)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGINT,self._on_stop_signal)
    def _on_stop_signal(self): self.quit(); return GLib.SOURCE_REMOVE
    def do_activate(self):
        first=self.window is None
        self.refresh_data(rebuild=False)
        if first:
            self._update_layout(False,False,focus_output=False); self.window=TVWCSWindow(self)
            self.apply_hotkeys(); GLib.timeout_add(1500,self._run_startup_action)
        self.window.set_visible(False)
    def do_shutdown(self):
        self._release_pid(); Gtk.Application.do_shutdown(self)
    def _claim_pid(self):
        try:
            PID_FILE.parent.mkdir(parents=True,exist_ok=True)
            if PID_FILE.exists():
                try: pid=int(PID_FILE.read_text().strip())
                except ValueError: pid=None
                if pid is not None and pid!=os.getpid() and is_tvwcs_process(pid):
                    print("TVWCS is already running.",file=sys.stderr); return False
            PID_FILE.write_text(str(os.getpid())); self._owns_pid=True; return True
        except OSError as exc: print(f"Cannot create PID file {PID_FILE}: {exc}",file=sys.stderr); return False
    def _release_pid(self):
        if self._owns_pid:
            try:
                if PID_FILE.read_text().strip()==str(os.getpid()): PID_FILE.unlink(missing_ok=True)
            except OSError: pass
    def refresh_data(self,rebuild=True):
        self.catalogue=ApplicationCatalogue.discover(); self.store.ensure_defaults(self.catalogue.applications)
        if rebuild and self.window is not None: self.window._build()

    # ---------------------------------------------------------- showing, hiding, geometry
    def _fallback_area(self):
        display=Gdk.Display.get_default()
        monitors=display.get_monitors() if display else None
        if monitors is not None and monitors.get_n_items():
            g=monitors.get_item(0).get_geometry(); return {"x":g.x,"y":g.y,"width":g.width,"height":g.height}
        return {"x":0,"y":0,"width":1920,"height":1080}
    def _update_layout(self,guide,options,focus_output=True):
        area=self.wm.usable_area(focus=focus_output) or self._fallback_area()
        s=self.store.settings; f=self.scale_factor
        self.layout=compute_layout(area,round(s["margin"]*f),round(s["quick_width"]*f),guide,options)
    def apply_geometry(self):
        """Ask i3 to float the window at the computed rectangle. Repeated shortly after mapping because
        i3 can only match the window once it exists."""
        if not self.wm.available or self.layout is None: return
        l=self.layout
        def place(): self.wm.place_tvwcs(l.x,l.y,l.width,l.height); return GLib.SOURCE_REMOVE
        for delay in (40,160,420): GLib.timeout_add(delay,place)
    def hide_window(self,launched=False):
        """Hide TVWCS, then make fullscreen again whatever was fullscreen when it was shown. `launched`: an app was just
        started, so nothing on the current workspace is made fullscreen over it."""
        if self.window is None: return
        shown=self.window.is_visible(); self.window.set_visible(False); self.window.note_shown()
        if shown and self._fullscreen:
            ids=self._fullscreen; self._fullscreen=set()
            GLib.timeout_add(150,lambda:(self.wm.restore_fullscreen(ids,skip_current=launched),GLib.SOURCE_REMOVE)[1])   # once i3 has refocused
    def has_dialogs(self):
        return any(w is not self.window and w.is_visible() for w in self.get_windows())
    def dismiss_dialogs(self):
        """Close every dialog (profile editor, application profiles, messages) without saving what is in it. Used when
        the TVWCS window is clicked while one is open: it then comes to the front, and a dialog left behind it would block it."""
        for w in list(self.get_windows()):
            if w is self.window or not w.is_visible(): continue
            discard=getattr(w,"discard",None)
            if discard is not None: discard()
            else: w.close()
    def has_4k_display(self):
        """True when a connected monitor is 4K (3840×2160) or larger."""
        display=Gdk.Display.get_default(); monitors=display.get_monitors() if display else None
        for i in range(monitors.get_n_items() if monitors is not None else 0):
            m=monitors.get_item(i); g=m.get_geometry(); f=max(1,m.get_scale_factor())
            if is_4k(g.width*f,g.height*f): return True
        return any(is_4k((o.get("rect") or {}).get("width",0),(o.get("rect") or {}).get("height",0)) for o in self.wm.outputs())

    def show_mode(self,mode):
        """'toggle' (the menu hotkey): show or hide the Quick Menu. 'guide' (the guide hotkey): open the Guide beside
        the Quick Menu, or close it again if it is already open."""
        w=self.window
        if w is None: return False
        visible=w.is_visible()
        if mode=="toggle" and visible: self.hide_window(); return False
        guide=(mode=="guide") and not (visible and w.guide_open)
        if visible: self.show_panels(guide,False,focus="guide" if guide else "quick"); return False
        self._fullscreen=self.wm.fullscreen_windows()   # restored when TVWCS hides (see hide_window)
        self.wm.focus_output_under_mouse(); self.wm.leave_fullscreen(); self.wm.move_tvwcs_to_current_workspace(); self.refresh_data(rebuild=False)
        w.reset_scroll(); w.note_shown(); w.guide_open=guide; w.options_open=False; w.apps_view="applications"   # always opens on the guide
        self._update_layout(guide,False,focus_output=True)
        w.set_default_size(self.layout.width,self.layout.height); w._build(); w.present(); self.apply_geometry()
        w.focus_pane_soon("guide" if guide else "quick")
        return False
    def show_panels(self,guide,options,focus=None):
        """Open or close the Guide / Settings panels of the visible window and resize it to fit."""
        w=self.window
        if w is None or not w.is_visible(): return
        self._update_layout(guide,options,focus_output=False)
        w.set_panels(guide,options); w.set_default_size(self.layout.width,self.layout.height); self.apply_geometry()
        if focus: w.focus_pane_soon(focus)
    def apply_scale(self):
        """The interface size changed: rebuild everything at the new size; the Applications pane stays on Settings."""
        set_scale(self.scale_factor); w=self.window
        self._update_layout(w.guide_open,w.options_open,focus_output=False)
        w.set_default_size(self.layout.width,self.layout.height); w._build(); self.apply_geometry(); w.focus_pane_soon("guide")

    # ---------------------------------------------------------- open windows and workspaces
    def workspace_entries(self): return build_entries(self.wm.windows(),self.wm.workspaces(),self.match_application_window)
    def default_profile(self,application):
        profiles=self.store.for_app(application.desktop_id)
        return next((p for p in profiles if p.name==application.name and not p.command and not p.desktop_action),profiles[0] if profiles else None)
    def match_application_window(self,window): return match_window(window,self.catalogue.applications)
    def window_icon(self,window,size=32,badge=None):
        app=self.match_application_window(window)
        spec=app.icon if app and app.icon else None
        if not spec:
            for candidate in (window.get("class"),window.get("instance")):
                if candidate and has_icon(candidate.lower()): spec=candidate.lower(); break
        return app_icon(spec,(app.name if app else None) or window.get("class") or window.get("title"),size,badge)
    def window_mode(self,window):
        """How selecting a running app places it: its own workspace, or tiled here. An app set to always launch in a new
        workspace always gets one; otherwise the 'open running apps in a new workspace' setting decides."""
        app=self.match_application_window(window); profile=self.default_profile(app) if app else None
        if self.store.settings["always_new_workspace"] or (profile and profile.launch_mode==LAUNCH_NEW_WORKSPACE): return LAUNCH_NEW_WORKSPACE
        return LAUNCH_NEW_WORKSPACE if self.store.settings["open_in_new_workspace"] else LAUNCH_SAME
    def launch_mode(self,profile):
        """Where a profile opens: its own setting, unless Settings says every app opens in a new workspace."""
        if self.store.settings["always_new_workspace"]: return LAUNCH_NEW_WORKSPACE
        return profile.launch_mode if profile else LAUNCH_SAME
    # PIN protection. A profile's PIN is asked when it is launched; if its scope is "launch and show" it is also asked
    # when an open window of it would be brought up from a workspace that is not on screen.
    def _with_pins(self,profiles,action):
        """Ask for each profile's PIN in turn, then run `action`."""
        if not profiles: action(); return
        self.window.ask_pin(profiles[0],lambda:self._with_pins(profiles[1:],action))
    def _window_profile(self,w):
        """The profile a window belongs to: the one that launched it, else its application's main profile."""
        owner=self.owners.owner(w["con_id"]); profile=self.store.get(owner) if owner else None
        if profile is None:
            app=self.match_application_window(w); profile=self.default_profile(app) if app else None
        return profile
    def _show_lock(self,w):
        p=self._window_profile(w)
        return p if p and p.pin_hash and p.pin_scope==PIN_LAUNCH_AND_SHOW and not w.get("workspace_visible") else None
    def _locks_for_workspace(self,name):
        locks=[]
        for w in self.wm.windows():
            if w["workspace"]==name:
                p=self._show_lock(w)
                if p and all(p.id!=q.id for q in locks): locks.append(p)
        return locks

    def focus_window(self,con_id,mode=None):
        w=next((x for x in self.wm.windows() if int(x["con_id"])==int(con_id)),None)
        if w is None: self.notify_message("Could not focus that window. It may have closed."); return
        lock=self._show_lock(w)
        self._with_pins([lock] if lock else [],lambda:self._focus_window_now(w,mode))
    def _focus_window_now(self,w,mode):
        if not self.wm.focus(w["con_id"],mode or self.window_mode(w)): self.notify_message("Could not focus that window. It may have closed."); return
        app=self.match_application_window(w); profile=self.default_profile(app) if app else None
        if profile: self.store.record_last_profile(profile.id)
        self.hide_window()
    def open_workspace(self,name):
        def go():
            if self.wm.focus_workspace(name): self.hide_window()
            else: self.notify_message("Could not switch to that workspace.")
        self._with_pins(self._locks_for_workspace(name),go)
    def move_workspace(self,name,output):
        def go():
            if self.wm.move_workspace_to_output(name,output): GLib.timeout_add(250,lambda:(self.refresh_data(rebuild=True),GLib.SOURCE_REMOVE)[1])
            else: self.notify_message("Could not move that workspace to another monitor.")
        self._with_pins(self._locks_for_workspace(name),go)   # moving can bring it on screen
    def close_workspace(self,entry):
        if not self.wm.close_workspace(entry.name): self.notify_message("Could not close every application on that workspace.")
        GLib.timeout_add(400,lambda:(self.refresh_data(rebuild=True),GLib.SOURCE_REMOVE)[1])

    # ---------------------------------------------------------- profiles and launching
    def toggle_favorite(self,profile):
        p=self.store.get(profile.id)
        if p: p.favorite=not p.favorite; self.store.save(); self.window.refresh_favorites(p.id)   # in place: no rebuild, no jump
    def edit_profile(self,profile,application):
        # A new profile is not stored until Save is pressed, so closing the editor cannot leave a half-created profile.
        if profile is None and application is not None:
            existing=self.store.for_app(application.desktop_id)
            editor=ProfileEditor(self,None,application)
            editor.name_entry.set_text(application.name if not existing else f"{application.name} profile {len(existing)+1}")
            editor.present(); return
        ProfileEditor(self,profile,application or self.catalogue.by_id().get(profile.desktop_id)).present()
    def edit_application_profiles(self,desktop_id): ApplicationProfilesWindow(self,desktop_id).present()
    def activate_result(self,result):
        if result["kind"]=="profile": self.launch_profile(result["profile"])
        elif result["kind"]=="window": self.focus_window(result["window"]["con_id"])
    def _launched(self,profile,started=False):
        self.store.record_last_profile(profile.id); self.hide_window(launched=started)
    def launch_profile(self,profile,bypass_pin=False):
        if profile is None: return
        app=self.catalogue.by_id().get(profile.desktop_id)
        # A plain profile returns to an existing window when it can; custom commands and desktop actions
        # run as written because they may stand for a separate session of the app.
        existing=None if (profile.command.strip() or profile.desktop_action) else self.wm.find_matching(profile,app)
        if existing is not None:
            needs_pin=profile.pin_scope==PIN_LAUNCH_AND_SHOW and not existing.get("workspace_visible")
            go=lambda:self._show_existing(profile,app,existing)
        else: needs_pin=True; go=lambda:self._start(profile,app)
        if profile.pin_hash and needs_pin and not bypass_pin: self.window.ask_pin(profile,go)
        else: go()
    def _show_existing(self,profile,app,window):
        if self.wm.focus(window["con_id"],self.launch_mode(profile)): self._launched(profile)
        else: self._start(profile,app)
    def _start(self,profile,app):
        known={int(w["con_id"]) for w in self.wm.windows()} if any(p.pin_hash for p in self.store.profiles) else None
        mode=self.launch_mode(profile)
        try:
            if profile.desktop_action and app:
                info=Gio.DesktopAppInfo.new(profile.desktop_id)
                if info is None: raise RuntimeError(f"No desktop launcher is available for {profile.desktop_id}.")
                self.wm.prepare_for_launch(mode); info.launch_action(profile.desktop_action,None)
            elif profile.command.strip():
                args=shlex.split(profile.command)
                if not args: raise ValueError("The custom launch command is empty.")
                self.wm.prepare_for_launch(mode)
                subprocess.Popen(args,start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            else:
                info=Gio.DesktopAppInfo.new(profile.desktop_id)
                if info is None: raise RuntimeError(f"No desktop launcher is available for {profile.desktop_id}.")
                self.wm.prepare_for_launch(mode)
                if not info.launch([],None): raise RuntimeError(f"Linux refused to launch {profile.name}.")
            if known is not None: self._remember_windows(profile,app,known)
            self._launched(profile,started=True)
        except (OSError,ValueError,RuntimeError) as exc: self.notify_message(f"Could not launch {profile.name}: {exc}")
    def _remember_windows(self,profile,app,known):
        """Note which windows this launch opened, so a later 'show' knows whose PIN applies. The app needs a moment to map them."""
        def claim():
            windows=self.wm.windows()
            self.owners.claim(known,windows,profile.id,lambda w:app is None or match_window(w,[app]) is app)
            self.owners.forget_closed(windows); return GLib.SOURCE_REMOVE
        for delay in (1500,4000,9000): GLib.timeout_add(delay,claim)
    def launch_action(self,application,action_id):
        profile=self.default_profile(application)
        def go():
            try:
                info=Gio.DesktopAppInfo.new(application.desktop_id)
                if info is None: raise RuntimeError("Desktop launcher is no longer available.")
                self.wm.prepare_for_launch(self.launch_mode(profile)); info.launch_action(action_id,None); self.hide_window(launched=True)
            except Exception as exc: self.notify_message(f"Could not launch desktop action: {exc}")
        # An action starts the application, so the main profile's PIN applies to it too.
        self._with_pins([profile] if profile and profile.pin_hash else [],go)
    def restart(self,launcher=None):
        """Start a fresh TVWCS once this process has exited (after an update replaced the program files), then quit.
        `launcher`: the new install's launcher, when the update moved TVWCS to another folder."""
        wait='while kill -0 "$1" 2>/dev/null; do sleep 0.2; done; exec "$2"'
        try: subprocess.Popen(["sh","-c",wait,"sh",str(os.getpid()),str(launcher or LAUNCHER)],start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except OSError as exc: self.notify_message(f"TVWCS was updated, but could not restart itself: {exc}. Restart it (or i3) to use the new version."); return
        self.hide_window(); self.quit()
    def run_system_action(self,action_id):
        command=command_for(action_id,self.store.settings)
        if not command:
            self.notify_message(unavailable_message(action_id)); return
        self.hide_window()
        power=action_id in POWER_VERBS; label=next((a.label for a in SYSTEM_ACTIONS if a.id==action_id),action_id)
        if power and privilege.needs_root(command): self._run_as_root(command,label); return
        def done(code,err):
            if code==0: return
            if power and privilege.polkit_refused(err): self._run_as_root(command,label); return   # no polkit agent to ask for a password
            self._failed(command,err)
        self._spawn(command,done,env=privilege.c_locale_env() if power else None)
    def _spawn(self,command,done,password=None,env=None):
        """Run a command without waiting for it; done(exit code, stderr) once it ends. `password` is written to its stdin."""
        try: proc=subprocess.Popen(command,start_new_session=True,env=env,stdin=subprocess.PIPE if password is not None else subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        except OSError as exc: self.notify_message(f"Could not run {command[0]}: {exc}"); return
        if password is not None:
            try: proc.stdin.write((password+"\n").encode()); proc.stdin.close()
            except OSError: pass   # it ended without reading it; its exit says why
        def finished(_pid,status):
            try: err=proc.stderr.read().decode(errors="replace").strip()[-300:]; proc.stderr.close()
            except (OSError,ValueError): err=""
            proc.returncode=code=os.waitstatus_to_exitcode(status)   # GLib reaped it; tell Popen
            done(code,err)
        GLib.child_watch_add(GLib.PRIORITY_DEFAULT,proc.pid,finished)
    def _failed(self,command,err):
        self.notify_message(f"{' '.join(command)} did not work{': '+err if err else '.'}")

    # Power actions that need root: a no-password doas or sudo rule (install.sh offers one), else the user's password.
    def _run_as_root(self,command,label):
        if os.geteuid()==0: self._spawn(command,lambda code,err:code and self._failed(command,err),env=privilege.c_locale_env()); return
        doas=privilege.doas_command(command)
        if doas: self._spawn(doas,lambda code,err:None if code==0 else self._sudo(command,label),env=privilege.c_locale_env())
        else: self._sudo(command,label)
    def _sudo(self,command,label):
        sudo=privilege.sudo_command(command)
        if sudo is None:
            self.notify_message(f"{label} needs administrator rights, and neither sudo nor a doas rule for it is available. "
                                "Install sudo, or run TVWCS's install.sh to set up a rule for it."); return
        def done(code,err):
            outcome=privilege.sudo_outcome(code,err)
            if outcome=="password": self._ask_root_password(command,label)
            elif outcome!="ok": self._sudo_failed(command,label,outcome,err)
        self._spawn(sudo,done,env=privilege.c_locale_env())
    def _ask_root_password(self,command,label,message="",tries=0):
        if self.window is None: return
        if not self.window.is_visible(): self.show_mode("toggle")   # the dialog is drawn in the TVWCS window
        self.window.ask_password(label,lambda password:self._sudo_with_password(command,label,password,tries),message)
    def _sudo_with_password(self,command,label,password,tries):
        self.hide_window()
        def done(code,err):
            outcome=privilege.sudo_outcome(code,err)
            if outcome=="wrong" and tries+1<PASSWORD_TRIES: self._ask_root_password(command,label,"Wrong password. Try again.",tries+1)
            elif outcome=="wrong": self.notify_message(f"{label}: the password was wrong {PASSWORD_TRIES} times.")
            elif outcome!="ok": self._sudo_failed(command,label,outcome,err)
        self._spawn(privilege.sudo_command(command,with_password=True),done,password=password,env=privilege.c_locale_env())
    def _sudo_failed(self,command,label,outcome,err):
        if outcome=="denied": self.notify_message(f"{label} needs administrator rights, and your user may not use sudo for it.")
        elif outcome=="tty": self.notify_message(f"{label}: sudo is set up to work only in a terminal (requiretty), so TVWCS cannot pass it a password.")
        else: self._failed(command,err)

    # ---------------------------------------------------------- hotkeys and start-up
    def set_hotkey(self,device,name,spec):
        """Set (or, with "", clear) one device's hotkey ("menu", "guide" or the remote's "fullscreen"). A key that
        something else had is taken from it (Settings asks first)."""
        self.store.set_slot_hotkey(device,name,spec); self.apply_hotkeys()
    def set_profile_hotkey(self,profile_id,spec):
        """Set (or, with "", clear) the hotkey that launches a profile, taking the key from whatever had it."""
        self.store.set_profile_hotkey(profile_id,spec); self.apply_hotkeys()
    def apply_hotkeys(self):
        """Write hotkeys.conf from the settings and the profiles' hotkeys, and ask i3 to reload if it changed."""
        text=render_i3(self.store.settings["hotkeys"],str(LAUNCHER),self._modifier_keycodes(),self.store.app_hotkeys())
        try: old=HOTKEYS_FILE.read_text(encoding="utf-8")
        except OSError: old=None
        if old!=text:
            try:
                HOTKEYS_FILE.parent.mkdir(parents=True,exist_ok=True); HOTKEYS_FILE.write_text(text,encoding="utf-8"); self.wm.reload()
            except OSError as exc: self.notify_message(f"Could not save the hotkeys: {exc}")
    @staticmethod
    def _modifier_keycodes():
        """This keyboard's keycodes for the left Super/Alt/Ctrl/Shift keys, as X reports them (missing ones use the defaults)."""
        display=Gdk.Display.get_default(); codes={}
        if display is None: return codes
        for mod,name in MODIFIER_KEYSYMS.items():
            try: ok,keys=display.map_keyval(Gdk.keyval_from_name(name))
            except (AttributeError,TypeError): continue
            if ok and keys: codes[mod]=min(k.keycode for k in keys)
        return codes
    def _take_requests(self):
        """Run the requests queued by `tvwcs launch <id>` (an application's hotkey)."""
        work=REQUESTS_FILE.with_name(REQUESTS_FILE.name+".work")
        try: REQUESTS_FILE.replace(work); lines=work.read_text(encoding="utf-8").splitlines(); work.unlink(missing_ok=True)
        except OSError: return
        for line in lines:
            parts=line.split()
            if len(parts)==2 and parts[0]=="launch": self.launch_by_hotkey(parts[1])
    def launch_by_hotkey(self,profile_id):
        profile=self.store.get(profile_id)
        if profile is None: self.apply_hotkeys(); return   # deleted since the hotkeys were written
        if profile.pin_hash and self.window is not None and not self.window.is_visible(): self.show_mode("toggle")   # the PIN keypad is drawn in the window
        self.launch_profile(profile)
    def _run_startup_action(self):
        """Once per login: open the chosen app, or whichever app was used last, and/or the Quick Menu."""
        if not first_time_this_login(STARTUP_MARKER): return GLib.SOURCE_REMOVE   # TVWCS was restarted during this login
        st=self.store.settings["startup"]
        profile=self.store.get(st["profile_id"]) if st["mode"]=="app" else self.store.get(st["last_profile_id"]) if st["mode"]=="last" else None
        if profile: self.launch_profile(profile,bypass_pin=True)   # chosen by the owner in Settings, so no PIN at login
        if st["show_menu"]:   # after the app has had a moment to map, so the menu opens over it rather than under it
            GLib.timeout_add(STARTUP_MENU_DELAY if profile else 0,self._show_startup_menu)
        return GLib.SOURCE_REMOVE
    def _show_startup_menu(self):
        if self.window is not None and not self.window.is_visible(): self.show_mode("toggle")
        return GLib.SOURCE_REMOVE

    def notify_message(self,message):
        # Gtk.MessageDialog exists on every GTK 4 release shipped by supported Mint/Debian/Ubuntu versions.
        d=Gtk.MessageDialog(application=self,transient_for=self.window,modal=True,message_type=Gtk.MessageType.ERROR,buttons=Gtk.ButtonsType.OK,text=message)
        d.connect("response",lambda w,*_:w.destroy()); d.present()

def send_signal(sig):
    try:
        pid=int(PID_FILE.read_text(encoding="ascii").strip()); os.kill(pid,sig); return 0
    except (OSError,ValueError) as exc:
        print(f"TVWCS is not running (or its PID file is stale): {exc}. Start `./tvwcs` first.",file=sys.stderr); return 1

def send_request(line):
    try:
        with open(REQUESTS_FILE,"a",encoding="utf-8") as f: f.write(line+"\n")
    except OSError as exc: print(f"Cannot queue the request in {REQUESTS_FILE}: {exc}",file=sys.stderr); return 1
    return send_signal(signal.SIGWINCH)

def main():
    args=sys.argv[1:]
    if args==["toggle"]: return send_signal(signal.SIGUSR1)
    if args==["guide"]: return send_signal(signal.SIGUSR2)
    if args==["stop"]: return send_signal(signal.SIGTERM)
    if len(args)==2 and args[0]=="launch" and args[1] and not any(c.isspace() for c in args[1]): return send_request(f"launch {args[1]}")
    if args[:1]==["control"] and len(args)<=2:   # the Control Panel, a separate application (optionally opened on one page)
        from tvwcs.ui_control import main as control_panel
        return control_panel(args[1:])
    if args: print("Usage: tvwcs [toggle|guide|stop|launch PROFILE_ID|control [PAGE]]",file=sys.stderr); return 2
    return TVWCSApp().run([])
if __name__=="__main__": raise SystemExit(main())
