"""The Settings app's pages. Each reads the system on a worker thread (control_* modules), then draws its rows;
a page that is on screen re-reads quietly every few seconds and only redraws when something changed, keeping the
selection on the same row."""
from __future__ import annotations
import os, signal, subprocess, time
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango

from tvwcs import control_bluetooth as bluetooth, control_flatpak as flatpak, control_display as display, control_ssh as ssh, control_network as network, control_sound as sound, control_sysinfo as sysinfo, control_updates as updates
from pathlib import Path
from tvwcs import __version__, power, privilege, selfupdate
from tvwcs.hotkeys import ACTION_LABELS, DEFAULT_HOTKEYS, DEVICE_ACTIONS, DEVICE_LABELS, DEVICES, describe
from tvwcs.model import SCALE_LABELS, STARTUP_LABELS, STARTUP_MODES, ConfigStore, apply_use, is_4k, scale_choices, startup_choices
from tvwcs.session import runtime_dir
from tvwcs.system_actions import command_for, login_manager_installed
from tvwcs.ui_control import StreamedRun, in_background
from tvwcs.widgets import NavGroup, S, clear_box, glyph, muted_label, section_title, usable

try:
    gi.require_version("Vte","3.91")
    from gi.repository import Vte
except (ImportError,ValueError):
    Vte=None

class Page:
    key=""; title=""; icon=""; fallback=""
    poll=0              # seconds between quiet re-reads while the page is on screen (0: only when asked)
    refreshable=True    # a ⟳ button at the top right re-reads the page

    def __init__(self, win):
        self.win=win; self.state=None; self.busy=False; self.status=""; self._loaded=False; self._poll=0
        self.header=[]; self.groups=[]; self._ids={}; self.root=None

    # ---------------------------------------------------------- frame
    def widget(self):
        root=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0); self.root=root
        head=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(14)); head.set_margin_top(S(12)); head.set_margin_start(S(24)); head.set_margin_end(S(24)); head.set_margin_bottom(S(6))
        title=Gtk.Label(label=self.title); title.add_css_class("pane-title"); title.set_xalign(0); head.append(title)
        self.subtitle=Gtk.Label(); self.subtitle.add_css_class("muted"); self.subtitle.set_valign(Gtk.Align.END); self.subtitle.set_margin_bottom(S(6))
        self.subtitle.set_xalign(0); self.subtitle.set_hexpand(True); self.subtitle.set_ellipsize(Pango.EllipsizeMode.END); head.append(self.subtitle)
        if self.refreshable:
            b=Gtk.Button(); b.add_css_class("square"); b.set_valign(Gtk.Align.START); b.set_child(glyph("view-refresh-symbolic","⟳")); b.set_tooltip_text("Check again")
            b.connect("clicked",lambda *_:self.refresh()); head.append(b); self.header=[b]
        root.append(head); root.append(self.content()); return root

    def content(self):
        scroll=Gtk.ScrolledWindow(); scroll.set_vexpand(True); scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        self.body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4)); self.body.set_margin_start(S(24)); self.body.set_margin_end(S(24)); self.body.set_margin_bottom(S(16))
        scroll.set_child(self.body); self.scroll=scroll; return scroll

    def nav_groups(self):
        return ([NavGroup(self.header)] if self.header else [])+self.groups
    def captures_keys(self, focused): return False

    # ---------------------------------------------------------- reading
    def shown(self):
        if not self._loaded: self._loaded=True; self.refresh()
        if self.poll and not self._poll: self._poll=GLib.timeout_add_seconds(self.poll,self._tick)
    def hidden(self):
        if self._poll: GLib.source_remove(self._poll); self._poll=0
    def _tick(self):
        if not self.busy and not self.win.modal_open and self.win.is_visible(): self.refresh(quiet=True)
        return GLib.SOURCE_CONTINUE
    def read(self): return None
    def refresh(self, quiet=False):
        if self.busy: return
        self.busy=True
        if not quiet: self.set_status("Checking…")
        def done(state):
            self.busy=False
            if not quiet: self.set_status("")
            if quiet and state==self.state: return
            self.state=state; self.redraw()
        def failed(exc):
            self.busy=False; self.set_status(""); self.win.notice(f"{self.title}",f"Could not read the settings: {exc}")
        in_background(self.read,done,failed)
    def set_status(self, text):
        self.status=text; self.subtitle.set_text(text or self.summary())
    def summary(self): return ""

    def act(self, work, status, title, after=None):
        """Change something on a worker thread: work() returns "" when it worked, else why not, which is shown.
        The page is read again afterwards."""
        self.set_status(status)
        def done(problem):
            self.set_status("")
            if problem: self.win.notice(title,problem)
            if after: after()
            self.busy=False; self.refresh(quiet=True)
        def failed(exc): done(str(exc))
        self.busy=True; in_background(work,done,failed)

    # ---------------------------------------------------------- drawing
    def redraw(self):
        """Draw the rows again from self.state, keeping the selection on the same row (by its id)."""
        focused=self.win.get_focus(); old=None
        if focused is not None and self.root is not None and (focused is self.root or focused.is_ancestor(self.root)):
            old=next((i for i,w in self._ids.items() if w is focused or focused.is_ancestor(w)),None)
        stale={id(w):i for i,w in self._ids.items()}
        wanted=getattr(self,"focus_after",None); self.focus_after=None   # the row a change turns the focused one into
        if wanted is not None and old is not None: old=wanted
        scroll=getattr(self,"scroll",None); top=scroll.get_vadjustment().get_value() if scroll is not None else 0
        clear_box(self.body); self.groups=[]; self._ids={}
        self.draw(self.state)
        if top and scroll is not None:   # rows drawn again (a dialog open over the page, say) stay where they were
            GLib.idle_add(lambda:(scroll.get_vadjustment().set_value(top),GLib.SOURCE_REMOVE)[1]); self.subtitle.set_text(self.status or self.summary())
        for widget_ref in ("_return_focus",):   # a dialog open over this page goes back to the row's new button
            w=getattr(self.win,widget_ref,None)
            if w is not None and id(w) in stale and stale[id(w)] in self._ids: setattr(self.win,widget_ref,self._ids[stale[id(w)]])
        last=self.win._last_page_focus.get(self.key)
        if last is not None and id(last) in stale and stale[id(last)] in self._ids: self.win._last_page_focus[self.key]=self._ids[stale[id(last)]]
        if old is not None:
            target=self._ids.get(old) or (next((w for i,w in self._ids.items() if i.startswith(old)),None) if old==wanted else None)
            if target is not None and usable(target): target.grab_focus()
            elif not self.win._focus_first(self.groups): self.win.tab_buttons[self.key].grab_focus()
    def draw(self, state): pass

    def add(self, widget): self.body.append(widget); return widget
    def section(self, text): return self.add(section_title(text))
    def note(self, text, css=None):
        l=muted_label(text)
        if css: l.add_css_class(css)
        return self.add(l)
    def register(self, *widgets, ident=None, column=False):
        g=NavGroup([w for w in widgets if w is not None]); g.column=column
        if g: self.groups.append(g)
        if ident is not None and g: self._ids[ident]=g[0]
        for k,w in enumerate(g[1:],1):
            if ident is not None: self._ids[f"{ident}#{k}"]=w
        return g

    def row(self, label, value="", on_activate=None, detail="", icon=None, fallback="", ident=None, extras=(), value_css="setting-value"):
        """One row: an optional icon, its name (and a detail line under it), its value on the right; square extra
        buttons follow it on the same row. ← / → move between them."""
        line=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(4))
        b=Gtk.Button(); b.add_css_class("launch-row"); b.set_hexpand(True)
        if on_activate is None: b.add_css_class("info-row")
        inner=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(14))
        if icon is not None or fallback:
            g=glyph(icon,fallback,24); g.set_size_request(S(32),-1); inner.append(g)
        text=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0); text.set_hexpand(True); text.set_valign(Gtk.Align.CENTER)
        name=Gtk.Label(label=label); name.set_xalign(0); name.set_ellipsize(Pango.EllipsizeMode.END); text.append(name)
        if detail:
            d=Gtk.Label(label=detail); d.add_css_class("row-detail"); d.set_xalign(0); d.set_ellipsize(Pango.EllipsizeMode.END); text.append(d)
        inner.append(text)
        if value:
            v=Gtk.Label(label=value); v.add_css_class(value_css); v.set_xalign(1); inner.append(v)
        b.set_child(inner)
        if on_activate is not None: b.connect("clicked",lambda *_:on_activate())
        line.append(b)
        extras=[e for e in extras if e is not None]
        for e in extras: e.add_css_class("square"); line.append(e)
        self.add(line); self.register(b,*extras,ident=ident); return b

    def button(self, icon, fallback, tooltip, handler, danger=False):
        b=Gtk.Button(); b.set_child(glyph(icon,fallback)); b.set_tooltip_text(tooltip); b.connect("clicked",lambda *_:handler())
        if danger: b.add_css_class("close-button")
        return b

def _on_off(flag): return "On" if flag else "Off"
def _outcome(result, otherwise):
    """A control_cmd.Result as act() wants it: "" when it worked, else why not."""
    return "" if result.ok else (result.message or otherwise)

# ====================================================================== Options (TVWCS's own)
def tell_tvwcs(request):
    """Ask the running TVWCS to read its options again ("reload") or to restart ("restart PATH"); False when it is not running.
    The same files and signal as main.send_request, written here rather than imported: after an update, main.py on disk
    is the new version, and importing it into this process (with the old versions of the other modules) can fail."""
    runtime=runtime_dir()
    try:
        pid=int((runtime/"tvwcs.pid").read_text(encoding="ascii").strip()); os.kill(pid,0)
        with open(runtime/"tvwcs-requests","a",encoding="utf-8") as f: f.write(request+"\n")
        os.kill(pid,signal.SIGWINCH); return True
    except (OSError,ValueError): return False   # not running: it reads its options when it starts

class OptionsPage(Page):
    """TVWCS's options: the Quick Menu's buttons, the interface size, behaviour, what opens at login, hotkeys and
    TVWCS's own updates. Each change is saved to TVWCS's config file, read fresh first so nothing TVWCS saved
    meanwhile is lost, and the running TVWCS is asked to read it again."""
    key="options"; title="Options"; icon="preferences-other-symbolic"; fallback="⚙"; refreshable=False
    def __init__(self, win):
        super().__init__(win); self.update_text=""; self.updating=False
    def read(self): return ConfigStore()
    def summary(self): return f"TVWCS {__version__}"
    def change(self, edit, notice=""):
        """edit(store) changes a freshly read store; it is saved, and TVWCS reads it again."""
        store=ConfigStore(); edit(store); store.save(); self.state=store; self.redraw()
        tell_tvwcs("reload")
        if notice: self.win.notice("Options",notice)
    def toggle(self, key):
        def edit(store): store.settings[key]=not store.settings[key]
        return lambda:self.change(edit)
    def option(self, label, key, hint="", invert=False):
        on=bool(self.state.settings[key])!=invert
        self.row(label,_on_off(on),self.toggle(key),ident=f"opt:{key}")
        if hint: self.note(hint)

    def draw(self, store):
        st=store.settings
        self.section("QUICK MENU")
        self.option("Settings button (⚙)","quick_settings_button","Opens this Settings app from the Quick Menu.")
        self.option("Close button (✕)","quick_close_button","Esc and the remote's Back key close the Quick Menu too.")
        locker=command_for("lock",st)
        self.option("Lock in the power menu","quick_lock_button",
                    "The power menu (⏻) always has Sleep, Reboot and Shut down"+(", and Log out, as this computer has a login screen." if login_manager_installed() else
                    ". It has no Log out here: without a login screen, logging out would only leave a text console.")
                    +("" if locker else " No screen locker is installed (such as i3lock, or swaylock on sway), so Lock would not work yet."))
        self.option("Options buttons on rows (☰)","hide_options_buttons","Even hidden, a row's options open by pressing ← on it, or by right-clicking it.",invert=True)
        self.option("Button hints","button_hints","Shows what a button with only an icon does when it has been selected for 3 seconds, for 6 seconds.")

        self.section("DISPLAY")
        self.row("Used on",{"tv":"A TV","desktop":"A desktop monitor"}.get(st["use"],"Not chosen"),self.choose_use,ident="opt:use")
        self.note("A TV: TV Mode size, every app opens in a workspace of its own, and an app alone on its workspace has no border. "
                  "A desktop monitor: Desktop size, and apps open tiled in the current workspace. Size and workspaces can still be "
                  "changed one by one below.")
        has_4k=self.has_4k()
        self.row("Interface size",SCALE_LABELS[st["scale"]],lambda:self.win.choose_option("Interface size",scale_choices(st["scale"],has_4k),st["scale"],self.pick_scale),ident="opt:scale")
        self.note("Desktop for a monitor at arm's length; TV Mode for a TV across the room"+("; 4K TV Mode for a 4K TV." if has_4k else ". 4K TV Mode is offered when a 4K display is connected."))

        self.section("BEHAVIOR")
        self.option("Close when clicking outside","close_on_click_outside")
        self.option("Always open apps in a new workspace","always_new_workspace",
                    "On: every app, whether you launch it or select it while it is open, gets a workspace of its own, whatever its profile says.")
        self.option("Open running apps in a new workspace","open_in_new_workspace",
                    "On: selecting an open app gives it a workspace of its own. Off: it is tiled into the current workspace.")

        self.section("AT LOGIN")
        names={p.id:p.name for p in store.profiles}
        mode=st["startup"]["mode"]
        self.row("Open at login",STARTUP_LABELS[mode],lambda:self.win.choose_option("Open at login",[(m,STARTUP_LABELS[m]) for m in STARTUP_MODES],
                 mode,lambda m:self.pick_startup(store,m)),ident="opt:startup")
        if mode=="app":
            self.row("Application",names.get(st["startup"]["profile_id"],"Not chosen"),lambda:self.choose_app(store),ident="opt:startup-app")
        self.note({"none":"Nothing opens by itself when you log in.","menu":"The Quick Menu opens when you log in.",
                   "last":"Whichever application you used most recently opens when you log in.",
                   "app":"The application chosen above opens when you log in."}[mode]+" It happens once per login, a moment after TVWCS starts.")

        hints={"keyboard":"A modifier tapped on its own (such as Super) triggers when it is released, so Super combinations keep working.",
               "remote":"Most remotes send ordinary keys; F2 suits many of them. Fullscreen switches the app you are using in and out of fullscreen.",
               "gamepad":"A gamepad needs a mapper such as AntiMicroX to turn its buttons into keys; then choose those keys here."}
        for device in DEVICES:
            self.section(f"{DEVICE_LABELS[device].upper()} HOTKEYS")
            for name in DEVICE_ACTIONS[device]:
                self.row(ACTION_LABELS[name],describe(st["hotkeys"][device][name]),lambda d=device,n=name:self.change_hotkey(store,d,n),ident=f"key:{device}:{name}")
            self.note(hints[device])
        self.row("Reset all hotkeys","Defaults",self.reset_hotkeys,ident="key:reset")
        self.note("Keyboard: tap Super. Remote: F2. Gamepad: none. Application hotkeys are kept, unless one uses a default key.")
        self.section("APPLICATION HOTKEYS")
        n=len(store.hotkey_profiles())
        self.row("Applications with a hotkey","None" if n==0 else f"{n} mapped",self.app_hotkeys,ident="key:apps")
        self.note("Give an application a hotkey in its launch profile (✎ in the applications guide). Open this to change or remove them.")

        self.section("TVWCS UPDATES")
        self.row("Check for updates",self.update_text or f"Version {__version__}",None if self.updating else self.check_updates,ident="opt:update")
        self.note(f"Looks for a newer release of TVWCS on GitHub ({selfupdate.GITHUB_REPO}) and offers to install it.")
        self.option("Include prereleases","update_prereleases",
                    "Every change is released as a prerelease first, and marked as the latest release once it has been tested "
                    "on a TV computer. On: Check for updates offers prereleases too.")
        self.row("Roll back to the latest release","",None if self.updating else self.roll_back,ident="opt:rollback")
        self.note("Installs the release marked latest, even when it is older than this version: the way back from a prerelease.")

    def note(self, text, css=None):
        l=super().note(text,css); l.set_margin_bottom(S(6)); return l

    # ---------------------------------------------------------- choices
    def has_4k(self):
        gd=Gdk.Display.get_default(); monitors=gd.get_monitors() if gd else None
        for i in range(monitors.get_n_items() if monitors is not None else 0):
            m=monitors.get_item(i); g=m.get_geometry(); f=max(1,m.get_scale_factor())
            if is_4k(g.width*f,g.height*f): return True
        return False
    def pick_scale(self, key):
        self.change(lambda s:s.settings.update(scale=key),"TVWCS uses the new size now. Settings uses it the next time it opens.")
    def choose_use(self):
        def picked(use):
            old=self.state.settings["scale"]; self.change(lambda s:apply_use(s.settings,use))
            if self.state.settings["scale"]!=old: self.win.notice("Options","TVWCS uses the new size now. Settings uses it the next time it opens.")
        self.win.choose_option("Used on",[("tv","A TV, across the room"),("desktop","A desktop monitor, at arm's length")],self.state.settings["use"],picked)
    def pick_startup(self, store, mode):
        if mode=="app" and store.get(store.settings["startup"]["profile_id"]) is None: self.choose_app(store); return   # pick which one first
        self.change(lambda s:s.settings["startup"].update(mode=mode))
    def choose_app(self, store):
        options=[]
        for heading,profiles in startup_choices(store.profiles):
            for p in profiles: options.append((p.id,(f"{p.channel:03d}  " if p.channel is not None else "")+p.name+("  ★" if p.favorite else "")))
        if not options: self.win.notice("Chosen application","There are no applications to choose from yet."); return
        def picked(pid): self.change(lambda s:s.settings["startup"].update(profile_id=pid,mode="app"))
        self.win.choose_option("Open at login",options,store.settings["startup"]["profile_id"],picked)

    # ---------------------------------------------------------- hotkeys (TVWCS writes hotkeys.conf when it reads them again)
    def change_hotkey(self, store, device, name):
        label=f"{DEVICE_LABELS[device]}: {ACTION_LABELS[name]}"
        self.win.assign_hotkey(store,("slot",device,name),label,lambda spec:self.change(lambda s:s.set_slot_hotkey(device,name,spec)))
    def reset_hotkeys(self):
        def edit(s):
            for device in DEVICES:
                for name in DEVICE_ACTIONS[device]: s.set_slot_hotkey(device,name,DEFAULT_HOTKEYS[device][name])
        self.change(edit)
    def app_hotkeys(self):
        store=ConfigStore(); profiles=store.hotkey_profiles()
        if not profiles:
            self.win.notice("Application hotkeys","No application has a hotkey yet. Give one a hotkey in its launch profile (✎ in the applications guide)."); return
        def chosen(pid):
            p=store.get(pid)
            def set_key(spec): self.change(lambda s:s.set_profile_hotkey(pid,spec)); self.app_hotkeys()
            self.win.choose_option(p.name,[("change","Change the hotkey"),("remove","Remove the hotkey")],None,
                                   lambda what:self.win.assign_hotkey(store,("profile",pid),p.name,set_key,back=self.app_hotkeys) if what=="change" else set_key(""),
                                   back=self.app_hotkeys)
        self.win.choose_option("Application hotkeys",[(p.id,f"{p.name}  ·  {describe(p.hotkey)}") for p in profiles],None,chosen)

    # ---------------------------------------------------------- TVWCS's own updates
    def check_updates(self):
        self.updating=True; self.update_text="Checking…"; self.redraw()
        def failed(exc): self.updating=False; self.update_text="Check failed"; self.redraw(); self.win.notice("TVWCS updates",f"Could not check for updates: {exc}")
        prereleases=bool(ConfigStore().settings["update_prereleases"])
        in_background(lambda:selfupdate.latest_release(prereleases),self.checked,failed)
    def roll_back(self):
        self.updating=True; self.update_text="Checking…"; self.redraw()
        def failed(exc): self.updating=False; self.update_text="Check failed"; self.redraw(); self.win.notice("TVWCS updates",f"Could not check for updates: {exc}")
        def found(release):
            self.updating=False; self.update_text=""; self.redraw()
            if selfupdate.parse_version(release.version)==selfupdate.parse_version(__version__):
                self.win.notice("TVWCS updates",f"This is already the latest release, TVWCS {__version__}."); return
            dest=selfupdate.install_dir(Path(selfupdate.__file__).parent)
            if dest is None: self.win.notice("TVWCS updates","This copy runs from a source checkout: change its version with git."); return
            target=selfupdate.update_target(dest)
            self.win.confirm("Roll back TVWCS?",f"Install TVWCS {release.version}, the latest release, in place of {__version__}? "
                             "TVWCS restarts afterwards; your channels, favorites, options and hotkeys are kept.","Install "+release.version,
                             lambda:self.install(release,target,target!=dest),danger=False)
        in_background(selfupdate.latest_release,found,failed)
    def checked(self, release):
        self.updating=False
        if not selfupdate.is_newer(release.version,__version__): self.update_text=f"Up to date ({__version__})"; self.redraw(); return
        self.update_text=f"{release.version} available"; self.redraw()
        dest=selfupdate.install_dir(Path(selfupdate.__file__).parent)
        if dest is None:
            self.win.notice("TVWCS updates",f"TVWCS {release.version} is available. This copy runs from a source checkout: update it with git pull."); return
        target=selfupdate.update_target(dest); moving=target!=dest
        move=(f" It also moves TVWCS from {dest} to {target} and updates the include line in your i3 / sway config to match "
              "(the config is backed up first)." if moving else "")
        kind=" prerelease" if release.prerelease else ""
        self.win.confirm("Update TVWCS?",f"TVWCS {release.version}{kind} is available (you have {__version__}). Download and install it now?{move} "
                         "TVWCS restarts afterwards; your channels, favorites, options and hotkeys are kept.","Install update",
                         lambda:self.install(release,target,moving),danger=False)
    def install(self, release, target, moving):
        self.updating=True; self.update_text="Installing…"; self.redraw()
        def done(_out):
            self.updating=False; self.update_text=f"Installed {release.version}"; self.redraw()
            restarted=tell_tvwcs(f"restart {target/'bin'/'tvwcs'}")
            self.win.notice("TVWCS updated",f"TVWCS {release.version} is installed"+(" and has restarted." if restarted else ".")+
                            " Close Settings and open it again to use the new version.")
        def failed(exc): self.updating=False; self.update_text="Update failed"; self.redraw(); self.win.notice("TVWCS updates",f"The update failed: {exc}")
        in_background(lambda:selfupdate.install_release(release,target,migrate=moving),done,failed)

# ====================================================================== Power and sleep
class PowerPage(Page):
    """After how long without input the screen turns off, the computer locks and it sleeps (TVWCS keeps these times,
    see power.py), and what the system does by itself: X's blanking and DPMS, logind's idle action and the lid."""
    key="power"; title="Power and sleep"; icon="system-shutdown-symbolic"; fallback="⏻"
    def read(self):
        store=ConfigStore(); st=store.settings
        return power.read_state(st,command_for("lock",st) is not None,command_for("sleep",st) is not None)
    def summary(self): return "swayidle" if self.state and self.state.session=="sway" else ""
    def draw(self, s):
        times=s.settings
        self.section("WHEN NOTHING IS TOUCHED")
        screen=times["screen_off"]
        self.row(power.LABELS["screen_off"],self.system_screen_text(s) if screen is None else power.duration_text(screen),
                 lambda:self.choose("screen_off",screen,system=True),icon="video-display-symbolic",fallback="🖵",ident="idle:screen_off")
        self.row(power.LABELS["lock"],power.duration_text(times["lock"]),lambda:self.choose("lock",times["lock"]),
                 detail="" if s.locker else "No screen locker is installed (such as i3lock, or swaylock on sway)",
                 icon="system-lock-screen-symbolic",fallback="🔒",ident="idle:lock")
        self.row(power.LABELS["sleep"],power.duration_text(times["sleep"]),lambda:self.choose("sleep",times["sleep"]),
                 detail="" if s.can_sleep else "Nothing on this computer can make it sleep",
                 icon="weather-clear-night-symbolic",fallback="☾",ident="idle:sleep")
        self.note("Times count from the last key, remote button or mouse movement. Nothing happens while sound is playing, "
                  "or while an application keeps the computer awake.")
        if not s.idle_works and any(times[a] for a in power.ACTIONS):
            self.note("These times need swayidle on sway. Install it, then sign out and in again." if s.session=="sway" else
                      "TVWCS cannot tell how long the computer has been idle: install libxss1 (or xprintidle).","error")
        self.section("WHAT THE SYSTEM DOES BY ITSELF")
        if s.session=="X11":
            x=s.xtimers
            if not x.available: self.row("X screen saver and power saving","Unknown",None,detail="xset was not found, or there is no display")
            else:
                self.row("X blanks the screen after",power.duration_text(x.saver) if x.saver else "Never",None,
                         detail="X's own screen saver" + (" (switched off while TVWCS turns the screen off)" if screen is not None else ""),ident="sys:saver")
                self.row("X switches the monitor off after",power.duration_text(x.dpms_off) if x.dpms_off else "Never",None,
                         detail="DPMS power saving",ident="sys:dpms")
            if s.xss_lock:
                self.row("Locks when the screen turns off","Yes",self.stop_xss_lock if s.xss_lock!="?" else None,
                         detail="xss-lock is running"+(", started by your i3 config. Choose this to stop it" if s.xss_lock!="?" else
                                                       ". Remove it from the file that starts it to stop the screen locking"),
                         icon="system-lock-screen-symbolic",fallback="🔒",ident="sys:xss")
        l=s.logind
        if l.available:
            action={"ignore":"Nothing","suspend":"Sleep","hibernate":"Hibernate","hybrid-sleep":"Hybrid sleep","suspend-then-hibernate":"Sleep, then hibernate",
                    "poweroff":"Shut down","lock":"Lock"}.get(l.idle_action,l.idle_action)
            self.row("The system's idle action",action+(f" after {power.duration_text(l.idle_seconds)}" if l.idle_action!="ignore" and l.idle_seconds else ""),None,
                     detail="logind's IdleAction, set in /etc/systemd/logind.conf",ident="sys:logind")
            if l.lid: self.row("Closing the lid",{"suspend":"Sleep","ignore":"Nothing","poweroff":"Shut down","lock":"Lock","hibernate":"Hibernate"}.get(l.lid,l.lid),None,
                               detail="logind's HandleLidSwitch",ident="sys:lid")
        self.note("Change “Turn off the screen after” to let TVWCS decide instead of X. "
                  "logind's settings are changed in /etc/systemd/logind.conf, as root.")

    def stop_xss_lock(self):
        path=self.state.xss_lock
        self.win.confirm("Stop locking when the screen turns off",
                         "xss-lock locks the screen every time it turns off, even with “Lock after” set to Never, so a TV wakes up "
                         f"to a password prompt. TVWCS will turn it off in {path.replace(str(Path.home()),'~',1)} (keeping a copy of the file as "
                         f"{os.path.basename(path)}.before-tvwcs) and stop it now. “Lock after” still locks when you choose a time.",
                         "Stop it",lambda:self.act(lambda:power.stop_xss_lock(path),"Stopping xss-lock…","Power and sleep"),danger=False)

    @staticmethod
    def system_screen_text(s):
        if s.session=="sway": return "Never (sway)"
        x=s.xtimers; t=min([v for v in (x.saver,x.dpms_off) if v] or [0])
        return f"{power.duration_text(t)} (X)" if t else "Never (X)"

    def choose(self, action, current, system=False):
        options=([("system","Let the system decide")] if system else [])+[(str(v),power.duration_text(v)) for v in power.CHOICES]
        def picked(key):
            value=None if key=="system" else int(key)
            store=ConfigStore(); store.settings["idle"][action]=value; store.save(); tell_tvwcs("reload")
            if action in ("lock","sleep") and value and not (self.state.locker if action=="lock" else self.state.can_sleep):
                self.win.notice(power.LABELS[action].replace(" after",""),"Saved, but this computer has nothing to do that with yet.")
            self.refresh(quiet=True)
        self.win.choose_option(power.LABELS[action],options,"system" if current is None else str(current),picked)

# ====================================================================== Sound
class SoundPage(Page):
    key="sound"; title="Sound"; icon="audio-volume-high-symbolic"; fallback="🔊"; poll=3
    def read(self): return sound.read_state()
    def summary(self): return self.state.server if self.state and self.state.available else ""
    def draw(self, state):
        if not state.available: self.note(state.message); return
        self.section("OUTPUT")
        current=state.output()
        if current is None: self.note(self.no_output_text(state))
        else:
            self.volume_row(current,"out")
            for d in state.outputs: self.device_row(d,d.name==(current.name if current else ""),"audio-speakers-symbolic","🔈")
        for o in state.other_outputs: self.card_output_row(o)
        self.section("INPUT")
        current=state.input()
        if current is None: self.note("No microphone or other input is connected.")
        else:
            self.volume_row(current,"in")
            for d in state.inputs: self.device_row(d,d.name==current.name,"audio-input-microphone-symbolic","🎤")
        self.note("Choosing a device uses it from now on; sound that is already playing moves to it too.")

    def device_row(self, d, in_use, icon, fallback):
        ports=[p for p in d.ports if p.available]
        port=next((p.label for p in d.ports if p.name==d.active_port),"")
        extra=None
        if len(ports)>1:
            extra=self.button("view-list-symbolic","⋯",f"Choose the connector of {d.label}",lambda d=d,ports=ports:self.choose_port(d,ports))
        self.row(d.label,"In use" if in_use else "",(lambda d=d:self.act(lambda:_outcome(sound.make_default(d),"Could not switch to that device."),
                 f"Switching to {d.label}…","Sound")) if not in_use else None,
                 detail=port if len(ports)>1 else "",icon=icon,fallback=fallback,ident=f"{d.kind}:{d.name}",extras=[extra],
                 value_css="state-on")

    @staticmethod
    def no_output_text(state):
        if state.alsa_cards==0:
            return ("The computer has no sound card the system can use: its driver, or the firmware it needs, is missing. On Debian, "
                    "install firmware-sof-signed (Intel laptops and mini PCs) or firmware-misc-nonfree (from non-free-firmware), then restart.")
        return "No sound output was found."

    def card_output_row(self, o):
        """An output of a profile the card is not using now (often its HDMI output): choosing it switches the card over."""
        detail=f"{o.card_label} · "+("switches the sound card to this output" if o.available else "nothing seems plugged in here, but it can be tried")
        def use(o=o):
            self.act(lambda:_outcome(sound.use_card_output(o),f"Could not switch {o.card_label} to {o.label}."),f"Switching to {o.label}…",
                     "Sound",after=lambda:setattr(self,"focus_after",f"sink:{sound.sink_for(o.card,o.output)}"))
        self.row(o.label,"",use,detail=detail,icon="video-display-symbolic" if o.hdmi else "audio-speakers-symbolic",
                 fallback="🖵" if o.hdmi else "🔈",ident=f"card:{o.card}:{o.output}")

    def choose_port(self, d, ports):
        def picked(name): self.act(lambda:_outcome(sound.set_port(d,name),"Could not switch the connector."),"Switching…","Sound")
        self.win.choose_option(f"Connector · {d.label}",[(p.name,p.label) for p in ports],d.active_port,picked)

    def volume_row(self, d, ident):
        """− [ level ] + and mute. The bar can be dragged with a mouse; the D-pad uses − and +."""
        line=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(6)); line.set_margin_top(S(2)); line.set_margin_bottom(S(4))
        minus=self.button("list-remove-symbolic","−","Quieter",lambda:step(-1)); plus=self.button("list-add-symbolic","+","Louder",lambda:step(1))
        mute=Gtk.Button()
        scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,sound.MAX_VOLUME,1); scale.set_draw_value(False); scale.set_hexpand(True)
        scale.set_focusable(False); scale.set_valign(Gtk.Align.CENTER)
        value=Gtk.Label(); value.add_css_class("volume-value"); value.set_xalign(1)
        guard=[False]; pending=[0]
        def show():
            guard[0]=True; scale.set_value(d.volume); guard[0]=False
            value.set_text(f"{d.volume} %")
            (scale.add_css_class if d.muted else scale.remove_css_class)("muted")
            mute.set_child(glyph("audio-volume-muted-symbolic" if d.muted else "audio-volume-high-symbolic","🔇" if d.muted else "🔊"))
            mute.set_tooltip_text(("Unmute " if d.muted else "Mute ")+d.label)
            (mute.add_css_class if d.muted else mute.remove_css_class)("active")
        def applied(result, what):
            if result.ok: return
            self.win.notice("Sound",f"Could not {what} {d.label}: {result.message}"); self.refresh(quiet=True)
        def apply_volume():
            pending[0]=0; level=d.volume
            in_background(lambda:sound.set_volume(d,level),lambda r:applied(r,"change the volume of")); return GLib.SOURCE_REMOVE
        def step(direction):
            d.volume=sound.stepped(d.volume,direction); show()
            if pending[0]: GLib.source_remove(pending[0])
            pending[0]=GLib.timeout_add(120,apply_volume)   # holding the key sends one change, not twenty
        def dragged(*_):
            if guard[0]: return
            d.volume=int(scale.get_value()); value.set_text(f"{d.volume} %")
            if pending[0]: GLib.source_remove(pending[0])
            pending[0]=GLib.timeout_add(120,apply_volume)
        def toggle_mute():
            d.muted=not d.muted; show(); muted=d.muted
            in_background(lambda:sound.set_muted(d,muted),lambda r:applied(r,"mute" if muted else "unmute"))
        scale.connect("value-changed",dragged); mute.connect("clicked",lambda *_:toggle_mute())
        for w in (minus,plus,mute): w.add_css_class("square")
        label=Gtk.Label(label="Volume"); label.set_xalign(0); label.set_size_request(S(110),-1)
        for w in (label,minus,scale,value,plus,mute): line.append(w)
        show(); self.add(line); self.register(minus,plus,mute,ident=f"volume:{ident}")

# ====================================================================== Displays
class DisplaysPage(Page):
    """Resolution and refresh rate of each display; with several, which are on, where each one is and (X11) the
    primary one. A change that can leave a screen blank goes back by itself unless it is kept."""
    key="displays"; title="Displays"; icon="video-display-symbolic"; fallback="🖵"; poll=5
    KEEP_SECONDS=15
    def read(self):
        s=display.read_state()
        if s.available:
            names=self.monitor_names()
            for o in s.outputs: o.label=o.label or names.get(o.name,"")
        return s
    def monitor_names(self):
        """Connector -> the display's own name, from GDK (it reads the displays' EDID on X11)."""
        gd=Gdk.Display.get_default(); monitors=gd.get_monitors() if gd else None; names={}
        for i in range(monitors.get_n_items() if monitors is not None else 0):
            m=monitors.get_item(i); label=" ".join(x for x in ((m.get_manufacturer() or ""),(m.get_model() or "")) if x).strip()
            if m.get_connector() and label: names[m.get_connector()]=label
        return names
    def summary(self):
        s=self.state
        if not s or not s.available: return ""
        n=len(s.outputs); return f"{n} displays connected" if n>1 else "1 display connected"

    def draw(self, s):
        if not s.available: self.note(s.message); return
        outs=s.outputs; on=[o for o in outs if o.enabled]; where=display.placements(outs); ref=display.reference(outs)
        if len(outs)>1 and on: self.add(self.preview(outs))
        for i,o in enumerate(outs,1):
            self.section(f"{i} · {o.title}".upper()+(f"  ({o.name})" if o.label else ""))
            if len(outs)>1:
                self.row("Use this display",_on_off(o.enabled),lambda o=o:self.switch(o),ident=f"{o.name}:on")
            if not o.enabled: continue
            mode=o.mode()
            self.row("Resolution",(display.mode_text(mode) if mode else f"{o.width} × {o.height}")+(" (recommended)" if mode and mode.preferred else ""),
                     (lambda o=o:self.choose_mode(o)) if len(o.modes)>1 else None,ident=f"{o.name}:mode")
            rates=mode.rates if mode else []
            if o.rate or rates:
                self.row("Refresh rate",display.rate_text(o.rate) if o.rate else "—",(lambda o=o:self.choose_rate(o)) if len(rates)>1 else None,ident=f"{o.name}:rate")
            if len(on)>1:
                if o is ref:
                    other=next((x for x in on if where.get(x.name,("",""))[1]==o.name),None)
                    value=display.RELATION_TEXT[display.relation(o,other)].format(other.title) if other else ""
                else:
                    rel,anchor=where[o.name]; value=display.RELATION_TEXT[rel].format(next(x.title for x in outs if x.name==anchor))
                self.row("Position",value,lambda o=o:self.choose_place(o),ident=f"{o.name}:place")
                if s.can_set_primary:
                    self.row("Primary display","Yes" if o.primary else "No",(lambda o=o:self.change(o,False,primary=True)) if not o.primary else None,
                             detail="" if o.primary else "Make this the primary display",ident=f"{o.name}:primary")
        notes=[f"A new resolution, refresh rate or display switched on or off goes back after {self.KEEP_SECONDS} seconds unless you keep it, "
               "in case a display cannot show it."]
        if len(on)>1 and s.can_set_primary: notes.append("The primary display holds the status bar's tray and is where the session starts.")
        notes.append("What you keep is used again at the next log-in, as long as the same displays are connected.")
        self.note(" ".join(notes))

    def preview(self, outs):
        """The displays that are on, drawn where they are, each with the number of its section."""
        on=[(i,o) for i,o in enumerate(outs,1) if o.enabled]
        minx=min(o.x for _i,o in on); miny=min(o.y for _i,o in on)
        maxx=max(o.x+o.size[0] for _i,o in on); maxy=max(o.y+o.size[1] for _i,o in on)
        k=min(S(560)/max(1,maxx-minx),S(180)/max(1,maxy-miny))
        fixed=Gtk.Fixed(); fixed.set_halign(Gtk.Align.CENTER); fixed.set_margin_top(S(8)); fixed.set_margin_bottom(S(8))
        fixed.set_size_request(round((maxx-minx)*k)+S(16),round((maxy-miny)*k)+S(16)); seen={}
        for i,o in on:
            shift=seen.get((o.x,o.y),0); seen[(o.x,o.y)]=shift+1   # mirrored displays sit on each other: offset a little
            w,h=o.size; box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0); box.add_css_class("display-box")
            if o.primary: box.add_css_class("primary")
            box.set_size_request(max(S(24),round(w*k)),max(S(24),round(h*k))); box.set_overflow(Gtk.Overflow.HIDDEN)
            number=Gtk.Label(label=str(i)); number.add_css_class("display-number"); number.set_vexpand(True); box.append(number)
            name=Gtk.Label(label=o.title); name.add_css_class("display-name"); name.set_ellipsize(Pango.EllipsizeMode.END); name.set_margin_bottom(S(4))
            name.set_margin_start(S(4)); name.set_margin_end(S(4)); box.append(name)
            fixed.put(box,round((o.x-minx)*k)+shift*S(8),round((o.y-miny)*k)+shift*S(8))
        return fixed

    # ---------------------------------------------------------- choosing
    def choose_mode(self, o):
        mode=o.mode()
        self.win.choose_option(f"Resolution · {o.title}",[(m.key,display.mode_text(m)+(" (recommended)" if m.preferred else "")) for m in o.modes],
                               mode.key if mode else None,lambda key:self.change(o,True,mode=key))
    def choose_rate(self, o):
        mode=o.mode()
        self.win.choose_option(f"Refresh rate · {o.title}",[(r,display.rate_text(r)) for r in mode.rates],o.rate,lambda r:self.change(o,True,rate=r))
    def choose_place(self, o):
        where=display.placements(self.state.outputs).get(o.name)
        def picked(key): rel,anchor=key.split(":",1); self.change(o,False,place=(rel,anchor))
        self.win.choose_option(f"Position · {o.title}",display.choices(self.state.outputs,o),f"{where[0]}:{where[1]}" if where else None,picked)
    def switch(self, o):
        if o.enabled and sum(x.enabled for x in self.state.outputs)==1:
            self.win.notice("Displays","This is the only display that is on, so it stays on."); return
        self.change(o,True,enabled=not o.enabled)

    # ---------------------------------------------------------- changing
    def change(self, o, risky, **changes):
        """Apply a change to one display now. A risky one waits to be kept, else goes back; the rest are kept at once."""
        s=self.state; old=s.outputs; new=display.edited(old,o.name,**changes)
        self.set_status("Changing the displays…"); self.busy=True
        def done(problem):
            self.busy=False; self.set_status("")
            if problem: self.win.notice("Displays",problem); self.refresh(quiet=True)
            elif risky: GLib.timeout_add(600,lambda:(self.ask_keep(s,old,new),GLib.SOURCE_REMOVE)[1])   # let the screen settle first
            else: self.keep(s,new)
        in_background(lambda:display.apply(s,new),done,lambda exc:done(str(exc)))
    def ask_keep(self, s, old, new):
        def message(n): return f"Keep these display settings? They go back in {n} second{'s' if n!=1 else ''}."
        def undo():
            self.set_status("Going back…"); self.busy=True
            def done(problem):
                self.busy=False; self.set_status("")
                if problem: self.win.notice("Displays",f"Could not go back to the earlier settings: {problem}")
                self.refresh(quiet=True)
            in_background(lambda:display.apply(s,old),done,lambda exc:done(str(exc)))
        self.win.countdown("Displays",message,self.KEEP_SECONDS,"Keep",lambda:self.keep(s,new),"Go back",undo)
    def keep(self, s, outputs):
        try: display.save(s,outputs)
        except OSError as exc: self.win.notice("Displays",f"The change is in use, but could not be saved for the next log-in: {exc}")
        self.refresh(quiet=True)

# ====================================================================== Bluetooth
class BluetoothPage(Page):
    key="bluetooth"; title="Bluetooth"; icon="bluetooth-active-symbolic"; fallback="ᛒ"; poll=4
    scanning=False
    def read(self): return bluetooth.read_state()
    def summary(self):
        s=self.state
        if not s or not s.available: return ""
        return ("Searching for devices…" if self.scanning else f"Adapter {s.controller}")
    def draw(self, s):
        if not s.available: self.note(s.message); return
        self.row("Bluetooth",_on_off(s.powered),lambda:self.act(lambda:bluetooth.set_powered(not s.powered),
                 "Switching Bluetooth "+("off…" if s.powered else "on…"),"Bluetooth"),ident="power")
        if s.blocked: self.note("Bluetooth is switched off by rfkill (airplane mode); turning it on here lifts that.")
        if not s.powered: self.note("Turn Bluetooth on to connect headphones, speakers, game controllers and remotes."); return
        self.row("Search for devices","Searching…" if self.scanning else "",None if self.scanning else self.scan,
                 detail="Put the device in pairing mode first.",icon="edit-find-symbolic",fallback="⌕",ident="scan")
        self.section("MY DEVICES")
        if not s.paired: self.note("No device is paired yet. Search for devices, then choose one to pair it.")
        for d in s.paired: self.device_row(d)
        self.section("OTHER DEVICES")
        named=[d for d in s.nearby if d.name and d.name.replace("-",":").upper()!=d.address]
        if not named: self.note("None found yet. Choose Search for devices." if not self.scanning else "Looking…")
        for d in named: self.device_row(d)
        if len(named)<len(s.nearby): self.note(f"{len(s.nearby)-len(named)} unnamed devices nearby are not listed.")

    def device_row(self, d):
        icon,fallback,kind=d.kind
        detail=" · ".join(x for x in (kind,f"Battery {d.battery} %" if d.battery is not None else "",d.address) if x)
        if not d.paired:
            self.row(d.name,"Pair",lambda d=d:self.act(lambda:bluetooth.pair(d.address),f"Pairing with {d.name}…",f"Pair {d.name}"),
                     detail=detail,icon=icon,fallback=fallback,ident=f"bt:{d.address}"); return
        forget=self.button("user-trash-symbolic","✕",f"Forget {d.name}",lambda d=d:self.win.confirm(f"Forget {d.name}?",
                           f"{d.name} will be disconnected and unpaired. To use it again, pair it again.","Forget",
                           lambda:self.act(lambda:bluetooth.forget(d.address),f"Forgetting {d.name}…","Bluetooth")),danger=True)
        if d.connected:
            go=lambda d=d:self.act(lambda:bluetooth.disconnect(d.address),f"Disconnecting {d.name}…","Bluetooth")
        else:
            go=lambda d=d:self.act(lambda:bluetooth.connect(d.address),f"Connecting to {d.name}…",f"Connect {d.name}")
        self.row(d.name,"Connected" if d.connected else "Not connected",go,detail=detail,icon=icon,fallback=fallback,
                 ident=f"bt:{d.address}",extras=[forget],value_css="state-on" if d.connected else "setting-value")

    def scan(self):
        self.scanning=True; self.redraw(); self.set_status("Searching for devices…")
        def done(_result):
            self.scanning=False; self.set_status(""); self.busy=False; self.refresh(quiet=True)
        in_background(lambda:bluetooth.scan(),done,lambda _e:done(None))

# ====================================================================== Software updates
class _Console:
    """A read-only console under a page's rows, showing the output of what the page runs."""
    def console(self):
        if self.log is None:
            self.log=Gtk.TextView(); self.log.set_editable(False); self.log.set_cursor_visible(False); self.log.set_focusable(False)
            self.log.add_css_class("console"); self.log.set_wrap_mode(Gtk.WrapMode.WORD_CHAR); self.log.set_monospace(True)
            self.log_scroll=Gtk.ScrolledWindow(); self.log_scroll.set_child(self.log); self.log_scroll.set_min_content_height(S(280))
            self.log_scroll.add_css_class("console-frame"); self.log_scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.AUTOMATIC)
        if self.log_scroll.get_parent() is not None: self.log_scroll.get_parent().remove(self.log_scroll)
        return self.log_scroll
    def _append(self, line):
        buf=self.log.get_buffer(); buf.insert(buf.get_end_iter(),line+"\n")
        if buf.get_line_count()>2000: buf.delete(buf.get_start_iter(),buf.get_iter_at_line(buf.get_line_count()-2000)[1])
        GLib.idle_add(lambda:(self.log_scroll.get_vadjustment().set_value(self.log_scroll.get_vadjustment().get_upper()),GLib.SOURCE_REMOVE)[1])

class UpdatesPage(_Console, Page):
    key="updates"; title="Software updates"; icon="software-update-available-symbolic"; fallback="⇩"
    MAX_ROWS=300
    def __init__(self, win):
        super().__init__(win); self.running=None; self.log=None; self.fetched=None
        self.finished=None; self.outcome=None   # the run that just ended, until the page is read again; then what came of it
    def read(self):
        state=updates.read_state(); state.reboot=updates.reboot_needed()
        if self.fetched and (state.checked or 0)<self.fetched: state.checked=self.fetched   # unchanged lists keep their old date
        return state
    def summary(self):
        s=self.state
        if not s or not s.available or s.manager is None: return ""
        age=updates.age_text(s.checked)
        return s.manager.label+(f" · package lists from {age}" if age else "")
    def draw(self, s):
        if not s.available: self.note(s.message); return
        if self.running:
            self.row(self.running,"Working…",None,icon="emblem-synchronizing-symbolic",fallback="⟳",ident="running")
            self.note("Leave this running until it finishes. Settings can be closed; the update carries on.")
            self.add(self.console()); return
        self.row("Check for updates",f"{s.total} available" if s.total else "Up to date",self.refresh,ident="check",
                 icon="view-refresh-symbolic",fallback="⟳")
        m=s.manager
        if m is not None and m.refresh_argv:
            self.row("Download the latest package lists","",lambda:self.run_steps("Downloading package lists",[(list(m.refresh_argv),True)],fetch=True),
                     detail="Asks for your password, then checks again.",icon="folder-download-symbolic",fallback="⇩",ident="lists")
        if s.total:
            self.row(f"Install {s.total} update{'s' if s.total!=1 else ''}","",self.confirm_install,ident="install",
                     detail="Installs everything listed below." + (" Asks for your password." if s.updates else ""),
                     icon="software-update-available-symbolic",fallback="⇩")
        if getattr(s,"reboot",False):
            self.row("Restart to finish updating","",self.confirm_reboot,detail="Some updates are only used after a restart.",
                     icon="system-reboot-symbolic",fallback="↻",ident="reboot")
        for label,problem in s.problems: self.note(f"{label}: {problem}","error")
        if self.finished: self.outcome=self.outcome_text(self.finished,s); self.finished=None; self._append(f"\n✓ {self.outcome}")
        if self.outcome: self.note(self.outcome,"state-on")
        if self.log is not None and self.log.get_buffer().get_char_count():
            self.section("LAST RUN"); self.add(self.console())
        for title,items in ((f"{m.label.upper()} PACKAGES" if m else "PACKAGES",s.updates),("FLATPAK APPS",s.flatpak)):
            if not items: continue
            self.section(f"{title} ({len(items)})")
            for u in items[:self.MAX_ROWS]:
                self.row(u.name,f"{u.old} → {u.new}" if u.old else u.new,lambda u=u:self.details(u),detail=u.source,ident=f"pkg:{title}:{u.name}")
            if len(items)>self.MAX_ROWS: self.note(f"… and {len(items)-self.MAX_ROWS} more.")

    @staticmethod
    def outcome_text(label, s):
        """The line that says a run has finished and what it found, such as: Package lists downloaded at 23:05. Everything is up to date."""
        done={"Downloading package lists":"Package lists downloaded","Installing updates":"Updates installed"}.get(label,f"{label}: finished")
        found=f"{s.total} update{'s' if s.total!=1 else ''} available." if s.total else "Everything is up to date."
        return f"{done} at {time.strftime('%H:%M')}. {found}"

    def details(self, u):
        lines=[f"Version {u.new}"]+([f"Installed now: {u.old}"] if u.old else [])+([f"From: {u.source}"] if u.source else [])
        self.win.notice(u.name,"\n".join(lines))

    def confirm_install(self):
        s=self.state; parts=[]
        if s.updates: parts.append(f"{len(s.updates)} package{'s' if len(s.updates)!=1 else ''} from {s.manager.label}")
        if s.flatpak: parts.append(f"{len(s.flatpak)} Flatpak app{'s' if len(s.flatpak)!=1 else ''}")
        steps=[]
        if s.updates: steps.append((list(s.manager.install_argv),True))
        if s.flatpak: steps.append((list(updates.FLATPAK.install_argv),False))
        self.win.confirm("Install updates?",f"Install {' and '.join(parts)} now? Apps being updated may need to be restarted afterwards.",
                         "Install",lambda:self.run_steps("Installing updates",steps),danger=False)

    def run_steps(self, label, steps, fetch=False):
        """Run each (argv, as root) in turn, showing their output; stop at the first that fails."""
        self.running=label; self.outcome=None; self.console(); self.log.get_buffer().set_text(""); self.redraw(); self.set_status(label+"…")
        self.win._focus_first(self.groups)
        def finish(problem=""):
            self.running=None; self.set_status(""); self.redraw()
            if problem: self._append(f"\n✗ Stopped: {problem}"); self.win.notice(label,problem)
            else: self.finished=label   # said once the page has been read again, with what it found
            self.refresh()
        def next_step(i):
            if i>=len(steps):
                if fetch: self.fetched=time.time()
                finish(); return
            argv,root=steps[i]; self._append("$ "+" ".join(argv))
            def done(code,tail):
                if code!=0: finish(tail.strip().splitlines()[-1] if tail.strip() else f"It stopped with exit status {code}."); return
                next_step(i+1)
            if root: self.win.run_as_root(argv,label,self._append,done)
            else: StreamedRun(argv,self._append,done)
        next_step(0)

    def confirm_reboot(self):
        command=command_for("reboot")
        if not command: self.win.notice("Restart","Nothing on this system can restart it from here."); return
        def go():
            if privilege.needs_root(command): self.win.run_as_root(command,"Restart",lambda _l:None,lambda code,tail:code and self.win.notice("Restart",tail))
            else:
                def done(code,tail):
                    if code and privilege.polkit_refused(tail): self.win.run_as_root(command,"Restart",lambda _l:None,lambda c,t:c and self.win.notice("Restart",t))
                    elif code: self.win.notice("Restart",tail)
                StreamedRun(command,lambda _l:None,done)
        self.win.confirm("Restart now?","Restart the computer now? Unsaved work in open applications may be lost.","Restart",go)

# ====================================================================== Apps (Flatpak, from Flathub)
def _shorten(text, limit):
    """Text cut at a paragraph or sentence end near `limit` characters."""
    if len(text)<=limit: return text
    cut=text[:limit]; end=max(cut.rfind("\n\n"),cut.rfind(". ")+1)
    return (cut[:end] if end>limit//2 else cut.rsplit(" ",1)[0]+" …").rstrip()

class AppsPage(_Console, Page):
    """A store of Flathub's apps: a grid of tiles with their icons, by category or found by a search typed on the
    on-screen keyboard, and the installed apps. Selecting a tile shows the app, with Install, or Open and Remove."""
    key="apps"; title="Apps"; icon="system-software-install-symbolic"; fallback="▦"
    COLUMNS=4; STEP=24
    def __init__(self, win):
        super().__init__(win); self.log=None; self.view="featured"; self.query=""; self.limit=self.STEP
        self.running=None; self.outcome=None; self.tiles_from=0; self.refresh_focus=None
    def read(self): return flatpak.read_state()
    def redraw(self):
        super().redraw()
        if self.refresh_focus and not self.busy and not self.win.modal_open:
            self.focus_tiles(self.refresh_focus); self.refresh_focus=None
    def summary(self):
        s=self.state
        if not s or not s.flatpak: return ""
        return (f"{len(s.catalog)} apps on Flathub · " if s.catalog else "")+f"{len(s.installed)} installed"

    def draw(self, s):
        self.tiles_from=0
        if self.running:
            self.row(self.running,"Working…",None,icon="emblem-synchronizing-symbolic",fallback="⟳",ident="running")
            self.note("Leave this running until it finishes."); self.add(self.console()); return
        if not s.flatpak:
            argv=flatpak.install_flatpak_argv()
            self.row("Install Flatpak","",(lambda:self.run_steps("Installing Flatpak",[(argv,True)],"Flatpak is installed. Set up Flathub next.")) if argv else None,
                     detail="Installs Flatpak with the package manager. Asks for your password.",icon="system-software-install-symbolic",fallback="⇩",ident="get-flatpak")
            self.note("Apps here come from Flathub through Flatpak, which keeps each app with what it needs, apart from the system."
                      +("" if argv else " No supported package manager was found to install Flatpak with."))
            self.last_run(); return
        if s.catalog is not None: self.toolbar(s)
        if s.problem: self.note(s.problem,"error")
        if self.outcome: self.note(self.outcome,"state-on")
        if s.catalog is None:   # nothing to browse yet: setting Flathub up comes first; installed apps can still be removed
            if "system" in s.remote:
                self.row("Download Flathub's list of apps","",self.setup,detail="Flathub is set up on this computer, but its list of apps has not been downloaded.",
                         icon="folder-download-symbolic",fallback="⇩",ident="setup")
                self.note("This also adds Flathub for you, so apps install for you without a password. Flathub is where most Linux apps are "
                          "published, from Kodi and VLC to Steam and web browsers.")
            else:
                self.row("Set up Flathub","",self.setup,detail="Adds Flathub for you (no password needed) and downloads its list of apps.",
                         icon="folder-download-symbolic",fallback="⇩",ident="setup")
                self.note("Flathub is where most Linux apps are published, from Kodi and VLC to Steam and web browsers.")
            if s.installed: self.draw_apps(s,"installed")
        else: self.draw_apps(s,self.view)
        if s.catalog is not None and self.view!="installed":
            age=updates.age_text(s.catalog.updated)
            self.row("Download the list of apps again","",self.setup,detail=f"Downloaded {age}" if age else "",icon="view-refresh-symbolic",fallback="⟳",ident="setup")
        self.last_run()

    def last_run(self):
        if self.log is not None and self.log.get_buffer().get_char_count(): self.section("LAST RUN"); self.add(self.console())

    def toolbar(self, s):
        bar=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(6)); bar.set_homogeneous(True); bar.set_margin_bottom(S(4))
        made=[]
        for icon,fallback,label,handler,current in (
                ("system-search-symbolic","🔍",f"“{self.query}”" if self.view=="search" else "Search",self.ask_search,self.view=="search"),
                ("view-grid-symbolic","▦",flatpak.CATEGORY_LABELS.get(self.view,"Categories")+"  ▾",self.choose_category,self.view in flatpak.CATEGORY_LABELS),
                ("emblem-ok-symbolic","✓",f"Installed ({len(s.installed)})",lambda:self.show("installed"),self.view=="installed")):
            b=Gtk.Button(); b.add_css_class("app-tool")
            if current: b.add_css_class("current")
            line=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(10)); line.set_halign(Gtk.Align.CENTER)
            line.append(glyph(icon,fallback,20)); l=Gtk.Label(label=label); l.set_ellipsize(Pango.EllipsizeMode.END); line.append(l)
            b.set_child(line); b.connect("clicked",lambda _b,h=handler:h()); bar.append(b); made.append(b)
        self.add(bar); g=self.register(*made,ident="tool"); g.column=True

    def listed(self, s, view):
        if view=="installed":
            known=s.catalog.by_id if s.catalog else {}
            return sorted((known.get(i.id) or flatpak.App(i.id,i.name,version=i.version) for i in s.installed),key=lambda a:a.name.casefold())
        if s.catalog is None: return []
        return s.catalog.search(self.query) if view=="search" else s.catalog.category(view)

    def draw_apps(self, s, view):
        apps=self.listed(s,view)
        if view=="installed": heading="INSTALLED"
        elif view=="search": heading="RESULTS"
        else: heading=flatpak.CATEGORY_LABELS[view].upper()
        self.section(f"{heading} ({len(apps)})")
        if not apps:
            self.note({"installed":"No Flatpak apps are installed yet. Find one under Categories or Search.",
                       "search":"Nothing on Flathub matches that. Try fewer or other words."}.get(view,"Nothing here yet.")); return
        grid=Gtk.Grid(); grid.set_column_homogeneous(True); grid.set_row_spacing(S(8)); grid.set_column_spacing(S(8)); grid.set_margin_top(S(4))
        shown=apps[:self.limit]; self.tiles_from=len(self.groups)
        for start in range(0,len(shown),self.COLUMNS):
            row=[]
            for col,a in enumerate(shown[start:start+self.COLUMNS]):
                t=self.tile(a,s.is_installed(a.id)); grid.attach(t,col,start//self.COLUMNS,1,1); row.append(t)
            for col in range(len(row),self.COLUMNS): grid.attach(Gtk.Box(),col,start//self.COLUMNS,1,1)   # keeps the tiles their size
            g=self.register(*row); g.column=True
            for t,a in zip(row,shown[start:start+self.COLUMNS]): self._ids[f"app:{a.id}"]=t
        self.add(grid)
        if len(apps)>self.limit:
            self.row(f"Show more ({len(apps)-self.limit} more)","",lambda:self.more(apps),icon="go-down-symbolic",fallback="↓",ident="more")

    def app_icon(self, a, size):
        paths=[a.icon] if a.icon else []
        for base in (flatpak.user_dir(),flatpak.SYSTEM_DIR):   # an installed app's own icon, in whichever size it brought
            paths+=[str(base/f"exports/share/icons/hicolor/{d}/apps/{a.id}.{ext}") for d,ext in
                    (("128x128","png"),("256x256","png"),("scalable","svg"),("512x512","png"),("96x96","png"),("64x64","png"),("48x48","png"))]
        path=next((p for p in paths if os.path.isfile(p)),None)
        if path is None: return glyph("application-x-executable-symbolic","▦",size)
        img=Gtk.Image.new_from_file(path); img.set_pixel_size(S(size)); return img

    def tile(self, a, installed):
        b=Gtk.Button(); b.add_css_class("app-tile")
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4)); box.set_valign(Gtk.Align.START)
        icon=self.app_icon(a,64); icon.set_margin_bottom(S(4)); box.append(icon)
        name=Gtk.Label(label=a.name); name.add_css_class("app-name"); name.set_ellipsize(Pango.EllipsizeMode.END); name.set_max_width_chars(1); name.set_hexpand(True)
        box.append(name)
        summary=Gtk.Label(label=a.summary or (f"Version {a.version}" if a.version else a.id)); summary.add_css_class("row-detail"); summary.set_wrap(True); summary.set_wrap_mode(Pango.WrapMode.WORD_CHAR); summary.set_lines(2)
        summary.set_ellipsize(Pango.EllipsizeMode.END); summary.set_max_width_chars(1); summary.set_justify(Gtk.Justification.CENTER); box.append(summary)
        if installed: badge=Gtk.Label(label="Installed"); badge.add_css_class("state-on"); box.append(badge)
        b.set_child(box); b.set_tooltip_text(a.name); b.connect("clicked",lambda *_:self.details(a)); return b

    # ---------------------------------------------------------- choosing what is shown
    def show(self, view):
        self.view=view; self.limit=self.STEP; self.redraw(); GLib.idle_add(lambda:(self.focus_tiles(),GLib.SOURCE_REMOVE)[1])
    def focus_tiles(self, ident=None):
        target=self._ids.get(ident) if ident else None
        if target is not None and usable(target): target.grab_focus(); return
        if self.tiles_from: self.win._focus_first(self.groups[self.tiles_from:])
        else: self.win._focus_first(self.groups)
    def ask_search(self):
        def search(text):
            if not text.strip(): return
            self.query=" ".join(text.split()); self.show("search")
        self.win.ask_text("Search Flathub","Type an app's name, or what it does.",search,initial=self.query,ok_label="Search")
    def choose_category(self):
        s=self.state; options=[(k,f"{label} ({len(s.catalog.category(k))})" if s.catalog else label) for k,label,_c in flatpak.CATEGORIES]
        self.win.choose_option("Categories",options,self.view,self.show)
    def more(self, apps):
        first=apps[self.limit] if len(apps)>self.limit else None
        self.limit+=self.STEP; self.redraw()
        if first is not None: self.focus_tiles(f"app:{first.id}")

    # ---------------------------------------------------------- an app
    def details(self, a):
        s=self.state; inst=s.is_installed(a.id); win=self.win
        win._begin_modal(a.name)
        head=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(16)); head.set_margin_bottom(S(10))
        head.append(self.app_icon(a,96))
        facts=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(2)); facts.set_valign(Gtk.Align.CENTER)
        version=(inst.version if inst else "") or a.version
        lines=[a.developer," · ".join(x for x in (f"Version {version}" if version else "",a.license) if x)]
        if a.verified: lines.append("✓ Verified on Flathub")
        for text in lines:
            if text: l=Gtk.Label(label=text); l.set_xalign(0); l.add_css_class("muted"); facts.append(l)
        if inst: l=Gtk.Label(label="Installed"+(" for everyone on this computer" if inst.installation=="system" else "")); l.set_xalign(0); l.add_css_class("state-on"); facts.append(l)
        head.append(facts); win.modal_card.append(head)
        if a.summary: win._message(a.summary,"app-summary")
        if a.description: win._message(_shorten(a.description,600))
        if inst: specs=[("Open",lambda:self.open_app(a),"active"),("Remove",lambda:self.remove(a,inst),"danger"),("Close",win.close_modal,None)]
        else: specs=[("Install",lambda:self.install(a),"active"),("Close",win.close_modal,None)]
        made=win._buttons(*specs)
        win._finish_modal([made],win.close_modal,made[0] if inst else made[-1])   # Close first: a stray Enter never starts a download
    def install(self, a):
        self.win.close_modal(); s=self.state
        steps=([] if "user" in s.remote else [(flatpak.setup_argv()[0],False)])+[(flatpak.install_argv(a.id),False)]
        self.run_steps(f"Installing {a.name}",steps,f"{a.name} is installed. Open it here, or from the applications guide.",a.id)
    def remove(self, a, inst):
        argv,root=flatpak.uninstall_argv(inst)
        self.win.confirm(f"Remove {a.name}?",f"{a.name} is removed from this computer"+(" for everyone, and this asks for your password" if root else "")
                         +f". Its settings stay (in ~/.var/app/{a.id}), so installing it again keeps them.","Remove",
                         lambda:self.run_steps(f"Removing {a.name}",[(argv,root)],f"{a.name} was removed.",a.id),
                         back=lambda:self.details(a))
    def open_app(self, a):
        self.win.close_modal()
        try: subprocess.Popen(flatpak.run_argv(a.id),start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except OSError as exc: self.win.notice(a.name,f"Could not open {a.name}: {exc}"); return
        self.win.close()   # out of the way of the app
    def setup(self):
        self.run_steps("Setting up Flathub",[(argv,False) for argv in flatpak.setup_argv()],"Flathub is set up.")

    def run_steps(self, label, steps, success, app_id=None):
        """Run each (argv, as root) in turn, showing their output; stop at the first that fails."""
        self.running=label; self.outcome=None; self.console(); self.log.get_buffer().set_text(""); self.redraw(); self.set_status(label+"…")
        self.win._focus_first(self.groups)
        def finish(problem=""):
            self.running=None; self.set_status("")
            if problem: self._append(f"\n✗ Stopped: {problem}")
            else: self.outcome=success; self._append(f"\n✓ {success}")
            target=f"app:{app_id}" if app_id else "tiles"
            self.redraw(); self.focus_tiles(target); self.refresh_focus=target   # and again once the page has been read again
            if problem: self.win.notice(label,problem)
            self.refresh(quiet=True)
        def next_step(i):
            if i>=len(steps): finish(); return
            argv,root=steps[i]; self._append("$ "+" ".join(argv))
            def done(code,tail):
                if code!=0: finish(tail.strip().splitlines()[-1] if tail.strip() else f"It stopped with exit status {code}."); return
                next_step(i+1)
            if root: self.win.run_as_root(argv,label,self._append,done)
            else: StreamedRun(argv,self._append,done)
        next_step(0)

# ====================================================================== System information
class SystemPage(Page):
    key="system"; title="System information"; icon="computer-symbolic"; fallback="🖥"
    def read(self): return sysinfo.read_sections(),ssh.read_state()
    def summary(self): return ""
    def draw(self, state):
        sections,remote=state
        displays=self.displays()
        if displays: sections=sections[:2]+[("DISPLAYS",displays)]+sections[2:]
        for title,rows in sections:
            self.section(title)
            for i,(label,value) in enumerate(rows): self.row(label,value,None,ident=f"{title}:{label}:{i}")
        self.draw_ssh(remote)

    # ---------------------------------------------------------- SSH: signing in to this computer from another one
    def draw_ssh(self, s):
        self.section("REMOTE ACCESS (SSH)")
        if not s.installed:
            self.row("SSH server","Not installed",self.install_ssh if ssh.install_argv() else None,
                     detail="Install it to sign in to this computer from another one",ident="ssh:server"); return
        self.row("SSH server","On" if s.active else "Off",lambda:self.switch_ssh(s),
                 detail=("Starts with the computer" if s.enabled else "Stopped at the next restart") if s.active else
                        ("Starts with the computer" if s.enabled else "Turn it on to sign in from another computer"),
                 ident="ssh:server",value_css="state-on" if s.active else "setting-value")
        self.row("Sign in with","Keys only" if not s.passwords else "Password or key",lambda:self.choose_sign_in(s),
                 detail=f"{s.keys} key{'s' if s.keys!=1 else ''} added for {s.user}",ident="ssh:auth")
        self.row("Connect with",f"ssh {s.user}@{s.address}",None,ident="ssh:command")
        self.row("User",s.user,None,ident="ssh:user")
        self.row("Local name",s.local_name if s.mdns else f"{s.local_name} (not announced)",None,
                 detail="" if s.mdns else "Install avahi-daemon to reach this computer by name",ident="ssh:name")
        for i,(iface,address) in enumerate(s.addresses):
            self.row("IP address" if i==0 else "",address,None,detail=iface,ident=f"ssh:ip:{i}")
        if not s.addresses: self.row("IP address","Not connected to a network",None,ident="ssh:ip:0")

    def as_root(self, argv, label, status):
        """Run one of control_ssh's commands as root, then read the page again; its output is shown if it fails."""
        self.set_status(status); lines=[]
        def done(code,tail):
            self.set_status("")
            if code: self.win.notice("SSH",("\n".join(lines[-6:]) or tail or f"{label} did not work.").strip())
            self.refresh(quiet=True)
        self.win.run_as_root(argv,label,lines.append,done)
    def install_ssh(self):
        self.win.confirm("Install the SSH server?","This installs OpenSSH's server with the package manager. Turn it on here afterwards.",
                         "Install",lambda:self.as_root(ssh.install_argv(),"Installing the SSH server","Installing the SSH server…"),danger=False)
    def switch_ssh(self, s):
        if not s.unit: self.win.notice("SSH","Without systemd, start and stop the SSH server with your init system's own tools."); return
        if s.active:
            self.win.confirm("Turn SSH off?","Nobody can sign in from another computer until it is turned on again. "
                             "Connections open now stay open.","Turn off",lambda:self.as_root(ssh.service_argv(s,False),"Turning SSH off","Turning SSH off…"))
        else: self.as_root(ssh.service_argv(s,True),"Turning SSH on","Turning SSH on…")
    def choose_sign_in(self, s):
        def picked(key):
            allow=key=="password"
            if allow==s.passwords: return
            if not allow:
                problem=ssh.key_only_problem(s)
                if problem: self.win.notice("Keys only",problem); return
            self.as_root(ssh.passwords_argv(s,allow),"Changing how SSH signs in","Changing how SSH signs in…")
        self.win.choose_option("Sign in with",[("password","Password or key"),("keys",f"Keys only (safer; {s.keys} key{'s' if s.keys!=1 else ''} added)")],
                               "password" if s.passwords else "keys",picked)
    def displays(self):
        display=Gdk.Display.get_default(); monitors=display.get_monitors() if display else None; rows=[]
        for i in range(monitors.get_n_items() if monitors is not None else 0):
            m=monitors.get_item(i); g=m.get_geometry(); f=max(1,m.get_scale_factor()); hz=m.get_refresh_rate()/1000 if m.get_refresh_rate() else 0
            name=" ".join(x for x in ((m.get_manufacturer() or ""),(m.get_model() or "")) if x).strip() or (m.get_connector() or f"Display {i+1}")
            rows.append((name,f"{g.width*f} × {g.height*f}"+(f" at {hz:.0f} Hz" if hz else "")))
        return rows

# ====================================================================== Terminal
class TerminalPage(Page):
    key="terminal"; title="Terminal"; icon="utilities-terminal-symbolic"; fallback="▮"; refreshable=False
    enter_at_top=True   # coming in from the tabs lands on the buttons: once in the terminal, every arrow key is the shell's
    def __init__(self, win):
        super().__init__(win); self.terminal=None; self.child=None; self.process=None
    def summary(self): return os.environ.get("SHELL","/bin/sh") if Vte is not None else "Command console"

    def content(self):
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(6)); box.set_margin_start(S(24)); box.set_margin_end(S(24)); box.set_margin_bottom(S(16))
        bar=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(4)); box.append(bar)
        if Vte is not None:
            restart=Gtk.Button(label="New session"); restart.connect("clicked",lambda *_:self.start(restart=True))
            copy=Gtk.Button(label="Copy"); copy.connect("clicked",lambda *_:self.terminal.copy_clipboard_format(Vte.Format.TEXT))
            paste=Gtk.Button(label="Paste"); paste.connect("clicked",lambda *_:self.terminal.paste_clipboard())
            tab=Gtk.Button(label="Tab"); tab.set_tooltip_text("Send the Tab key to the shell (completes what you typed)")
            tab.connect("clicked",lambda *_:self.send(b"\t"))
            esc=Gtk.Button(label="Esc"); esc.set_tooltip_text("Send the Esc key to the shell")
            esc.connect("clicked",lambda *_:self.send(b"\x1b"))
            for b in (restart,copy,paste,tab,esc): bar.append(b)
            hint=muted_label("↓ goes into the terminal, where every key goes to the shell. Esc or Back comes back up to these buttons. "
                             "Ctrl+Shift+C and Ctrl+Shift+V copy and paste.")
            hint.set_hexpand(True); hint.set_margin_start(S(12)); bar.append(hint)
            self.terminal=Vte.Terminal(); self.terminal.set_vexpand(True); self.terminal.set_hexpand(True)
            self.terminal.set_font_scale(max(1.0,self.win.app.scale)); self.terminal.set_scrollback_lines(5000)
            fg=Gdk.RGBA(); fg.parse("#d0d0d0"); bg=Gdk.RGBA(); bg.parse("#0c0c0c"); self.terminal.set_colors(fg,bg,None)
            self.terminal.connect("child-exited",self._exited)
            keys=Gtk.EventControllerKey(); keys.connect("key-pressed",self._terminal_key); self.terminal.add_controller(keys)
            frame=Gtk.Box(); frame.add_css_class("console-frame"); frame.append(self.terminal); box.append(frame)
            self.groups=[NavGroup([restart,copy,paste,tab,esc]),NavGroup([self.terminal])]
        else:
            self.entry=Gtk.Entry(); self.entry.set_hexpand(True); self.entry.set_placeholder_text("Type a command, then Enter")
            self.entry.connect("activate",lambda *_:self.run_command(self.entry.get_text()))
            run=Gtk.Button(label="Run"); run.add_css_class("active"); run.connect("clicked",lambda *_:self.run_command(self.entry.get_text()))
            stop=Gtk.Button(label="Stop"); stop.connect("clicked",lambda *_:self.process and self.process.stop())
            keyboard=Gtk.Button(); keyboard.set_child(glyph("input-keyboard-symbolic","⌨")); keyboard.add_css_class("square"); keyboard.set_tooltip_text("Type the command on the on-screen keyboard")
            keyboard.connect("clicked",lambda *_:self.win.ask_text("Command","Runs with sh -c in your home folder.",self.run_command,self.entry.get_text(),ok_label="Run"))
            for w in (self.entry,run,stop,keyboard): bar.append(w)
            box.append(muted_label("A full terminal needs VTE for GTK 4 (gir1.2-vte-3.91, vte4 or vte291-gtk4). Until then commands run here one at a time, without input."))
            self.output=Gtk.TextView(); self.output.set_editable(False); self.output.set_cursor_visible(False); self.output.set_focusable(False)
            self.output.add_css_class("console"); self.output.set_monospace(True); self.output.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            scroll=Gtk.ScrolledWindow(); scroll.set_vexpand(True); scroll.set_child(self.output); scroll.add_css_class("console-frame"); self.output_scroll=scroll; box.append(scroll)
            self.groups=[NavGroup([self.entry,run,stop,keyboard])]
        return box

    def redraw(self): pass   # nothing here is drawn from a state
    def shown(self):
        if Vte is not None and self.child is None: self.start()
    def captures_keys(self, focused):
        return self.terminal is not None and focused is not None and (focused is self.terminal or focused.is_ancestor(self.terminal))

    def start(self, restart=False):
        if restart and self.child:
            try: os.kill(self.child,9)
            except OSError: pass
        self.child=None; self.terminal.reset(True,True)
        shell=os.environ.get("SHELL") or "/bin/sh"
        def spawned(_term,pid,error,*_):
            if error is not None or pid<0: self.terminal.feed(f"Could not start {shell}: {error.message if error else ''}\r\n".encode()); return
            self.child=pid
        self.terminal.spawn_async(Vte.PtyFlags.DEFAULT,os.path.expanduser("~"),[shell],None,GLib.SpawnFlags.DEFAULT,None,None,-1,None,spawned)
        if restart: self.terminal.grab_focus()
    def send(self, data):
        """Type a key the remote has no button for (Tab, Esc) into the shell. The selection stays on the button, so it
        can be pressed again (Tab twice lists the completions)."""
        if self.child is not None: self.terminal.feed_child(list(data))
    def _exited(self, *_):
        self.child=None; self.terminal.feed(b"\r\n[The shell has ended. Choose New session to start another.]\r\n")
    def _terminal_key(self, _controller, keyval, _keycode, state):
        ctrl_shift=Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.SHIFT_MASK
        if state & ctrl_shift==ctrl_shift and keyval in (Gdk.KEY_C,Gdk.KEY_c): self.terminal.copy_clipboard_format(Vte.Format.TEXT); return True
        if state & ctrl_shift==ctrl_shift and keyval in (Gdk.KEY_V,Gdk.KEY_v): self.terminal.paste_clipboard(); return True
        return False

    def run_command(self, command):
        command=(command or "").strip()
        if not command: return
        if self.process is not None and self.process.proc is not None and self.process.proc.poll() is None:
            self.win.notice("Terminal","A command is still running. Stop it first."); return
        self.entry.set_text(""); self._out(f"$ {command}")
        def done(code,_tail):
            self.process=None; self._out(f"[exit status {code}]\n" if code else "")
        self.process=StreamedRun(["sh","-c",f"cd ~ && {command}"],self._out,done,env=None)
    def _out(self, line):
        if not line: return
        buf=self.output.get_buffer(); buf.insert(buf.get_end_iter(),line+"\n")
        GLib.idle_add(lambda:(self.output_scroll.get_vadjustment().set_value(self.output_scroll.get_vadjustment().get_upper()),GLib.SOURCE_REMOVE)[1])

# ====================================================================== Network
class NetworkPage(Page):
    key="network"; title="Network"; icon="network-wired-symbolic"; fallback="⇄"; poll=6
    scanning=False
    def read(self): return network.read_state(scan=self.scanning)
    def summary(self):
        s=self.state
        if not s: return ""
        return "NetworkManager" if s.managed else "Shown only (no NetworkManager)"
    def draw(self, s):
        if not s.managed: self.note(s.message)
        self.section("ETHERNET")
        wired=s.of_kind("ethernet")
        if not wired: self.note("No Ethernet port was found.")
        for i in wired: self.ethernet_row(i,s.managed)
        self.section("WI-FI")
        wireless=s.of_kind("wifi")
        if not wireless: self.note("No Wi-Fi adapter was found."); return
        if not s.managed:
            for i in wireless: self.ethernet_row(i,False)
            return
        self.row("Wi-Fi",_on_off(s.wifi_enabled),lambda:self.act(lambda:network.set_wifi(not s.wifi_enabled),
                 "Switching Wi-Fi "+("off…" if s.wifi_enabled else "on…"),"Wi-Fi"),icon="network-wireless-symbolic",fallback="📶",ident="wifi")
        if not s.wifi_enabled: return
        device=wireless[0]
        if device.connected: self.ip_row(device)
        self.row("Search for networks","Searching…" if self.scanning else "",None if self.scanning else self.scan,icon="edit-find-symbolic",fallback="⌕",
                 detail="Looks for Wi-Fi networks nearby. The list is not searched again until you choose this.",ident="scan")
        if not s.networks: self.note("Looking…" if self.scanning else "No networks listed. Choose Search for networks to look for them.")
        for n in s.networks: self.wifi_row(n,device)

    @staticmethod
    def _details(i):
        return " · ".join(x for x in (", ".join(i.addresses),f"Gateway {i.gateway}" if i.gateway else "",
                                       f"DNS {', '.join(i.dns)}" if i.dns else "",f"MAC {i.mac}" if i.mac else "") if x)
    @staticmethod
    def _state_text(i):
        if i.connected: return "Connected"
        return {"unavailable":"No cable","disconnected":"Not connected","unmanaged":"Not managed"}.get(i.state.split(" ")[0],i.state.capitalize() or "Unknown")

    def ethernet_row(self, i, managed):
        go=None; extras=[]
        if managed and i.state not in ("unavailable","unmanaged"):
            if i.connected:
                go=lambda i=i:self.win.confirm(f"Disconnect {i.device}?",f"Disconnect {i.connection or i.device}? Anything using the network will lose it until you connect again.",
                                               "Disconnect",lambda:self.act(lambda:network.disconnect_device(i.device),f"Disconnecting {i.device}…","Ethernet"))
            else: go=lambda i=i:self.act(lambda:network.connect_device(i.device),f"Connecting {i.device}…","Ethernet")
        label=("Ethernet" if i.kind=="ethernet" else "Wi-Fi")+f" ({i.device})"
        self.row(label,self._state_text(i),go,detail=self._details(i),icon="network-wired-symbolic" if i.kind=="ethernet" else "network-wireless-symbolic",
                 fallback="⇄",ident=f"if:{i.device}",extras=extras,value_css="state-on" if i.connected else "setting-value")
        if managed: self.ip_row(i)

    def ip_row(self, i):
        """IP address, default gateway and DNS servers of the interface's connection: from DHCP, or set by hand."""
        if not i.connection_uuid: return
        value="Automatic (DHCP)" if i.method!="manual" else "Fixed"+(f": {i.addresses[0].split('/')[0]}" if i.addresses else "")
        self.row(f"IP settings ({i.device})",value,lambda i=i:self.ip_settings(i),icon="preferences-system-network-symbolic",fallback="⚙",
                 detail="IP address, default gateway and DNS servers, or back to automatic (DHCP)",ident=f"ip:{i.device}")

    def wifi_row(self, n, device):
        detail=f"{network.signal_bars(n.signal)}  {n.signal} %"+(f" · {n.security}" if n.secured else " · Open")
        if n.in_use and device.addresses: detail+=" · "+self._details(device)
        extras=[]
        if n.saved_uuid:
            extras.append(self.button("user-trash-symbolic","✕",f"Forget {n.ssid}",lambda n=n:self.win.confirm(f"Forget {n.ssid}?",
                          f"The saved password and settings for {n.ssid} are removed"+(", and this computer leaves it." if n.in_use else "."),
                          "Forget",lambda:self.act(lambda:network.forget(n.saved_uuid),f"Forgetting {n.ssid}…","Wi-Fi")),danger=True))
        if n.in_use:
            go=lambda n=n:self.win.confirm(f"Disconnect from {n.ssid}?","Anything using the network will lose it until you connect again.","Disconnect",
                                          lambda:self.act(lambda:network.disconnect_device(device.device),f"Disconnecting from {n.ssid}…","Wi-Fi"))
        elif n.saved_uuid: go=lambda n=n:self.act(lambda:network.activate(n.saved_uuid),f"Connecting to {n.ssid}…",f"Connect to {n.ssid}")
        elif n.secured: go=lambda n=n:self.ask_password(n)
        else: go=lambda n=n:self.act(lambda:network.join_wifi(n.ssid),f"Connecting to {n.ssid}…",f"Connect to {n.ssid}")
        locked=n.secured
        self.row(n.ssid,"Connected" if n.in_use else "Saved" if n.saved_uuid else "",go,detail=detail,
                 icon="network-wireless-encrypted-symbolic" if locked else "network-wireless-symbolic",fallback="🔒" if locked else "📶",
                 ident=f"wifi:{n.ssid}",extras=extras,value_css="state-on" if n.in_use else "setting-value")

    def ask_password(self, n, error=""):
        def join(password):
            if not password: return
            def work():
                problem=network.join_wifi(n.ssid,password)
                if problem!="The password was not accepted.": return problem
                GLib.idle_add(lambda:(self.ask_password(n,"The password was not accepted. Try again."),GLib.SOURCE_REMOVE)[1]); return ""
            self.act(work,f"Connecting to {n.ssid}…",f"Connect to {n.ssid}")
        self.win.ask_text(f"Password for {n.ssid}",f"{n.security} network. NetworkManager saves the password for next time.",join,secret=True,ok_label="Connect",error=error)

    def scan(self):
        self.scanning=True; self.redraw(); self.set_status("Searching for networks…")
        def done(state):
            self.scanning=False; self.busy=False; self.set_status("")
            if state is not None: self.state=state
            self.redraw()
        self.busy=True; in_background(lambda:network.read_state(scan=True),done,lambda _e:done(None))

    def ip_settings(self, i):
        uuid,name=i.connection_uuid,i.connection or i.device
        self.set_status("Reading IP settings…")
        in_background(lambda:network.read_ipv4(uuid),lambda s:(self.set_status(""),self.ip_form(uuid,name,s,iface=i)))
    def ip_form(self, uuid, name, s, error="", iface=None):
        again=lambda error="":self.ip_form(uuid,name,s,error,iface)
        def edit(field,title,message):
            def set_value(text): setattr(s,field,text.strip()); again()
            self.win.ask_text(title,message,set_value,getattr(s,field),back=lambda:again())
        def flip():
            nonlocal s
            s=network.Ipv4Settings("auto",s.address,s.gateway,s.dns) if not s.automatic else network.fixed_from(s,iface)
            again()
        rows=[("Get the settings automatically (DHCP)","Yes" if s.automatic else "No, set them here",flip)]
        if not s.automatic:
            rows+=[("IP address",s.address,lambda:edit("address","IP address","With its prefix, for example 192.168.1.20/24 (without one, /24 is used).")),
                   ("Default gateway",s.gateway,lambda:edit("gateway","Default gateway","The router's address, for example 192.168.1.1. Can be left empty.")),
                   ("DNS servers",s.dns,lambda:edit("dns","DNS servers","One or more, separated by commas, for example 1.1.1.1, 9.9.9.9."))]
        def save():
            problem,_args=network.validate_ipv4(s)
            if problem: again(problem); return
            self.win.close_modal()
            self.act(lambda:network.apply_ipv4(uuid,s),f"Applying the IP settings of {name}…","IP settings")
        self.win.form(f"IP settings · {name}",rows,"Save",save,
                      "Automatic (DHCP) asks the router for the address, gateway and DNS servers; choose the first row to switch. "
                      "Saving reconnects, so the connection drops for a moment.",error)

PAGES=(OptionsPage,SoundPage,DisplaysPage,PowerPage,BluetoothPage,AppsPage,UpdatesPage,SystemPage,TerminalPage,NetworkPage)
