"""The Settings app's pages. Each reads the system on a worker thread (control_* modules), then draws its rows;
a page that is on screen re-reads quietly every few seconds and only redraws when something changed, keeping the
selection on the same row."""
from __future__ import annotations
import math, os, shutil, signal, subprocess, time
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango

from tvwcs import control_storage as storage
from tvwcs import control_bluetooth as bluetooth, control_datetime as timedate, control_flatpak as flatpak, control_display as display, control_ssh as ssh, control_network as network, control_sound as sound, control_sysinfo as sysinfo, control_updates as updates
from pathlib import Path
from tvwcs import __version__, features, power, privilege, selfupdate
from tvwcs import ui_control_login as login_ui
from tvwcs.hotkeys import ACTION_LABELS, DEFAULT_HOTKEYS, DEVICE_ACTIONS, DEVICE_LABELS, DEVICES, describe
from tvwcs.model import (SCALE_LABELS, SCREENSAVER_LOGOS, THEMES, WALLPAPERS, ConfigStore, accent_name, is_4k, scale_choices,
                         scale_key, tv_mode)
from tvwcs.session import runtime_dir
from tvwcs.system_actions import command_for
from tvwcs.ui_control import StreamedRun, colour_swatch, in_background
from tvwcs.widgets import METRO_COLORS, NavGroup, S, clear_box, glyph, muted_label, section_title, usable

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
    def feature_off(self):
        """The software this page needs (features.py) is not installed: the page only offers to install it."""
        key=features.PAGE_FEATURE.get(self.key)
        return key is not None and not features.installed(features.BY_KEY[key])
    def refresh(self, quiet=False):
        if self.feature_off():
            if not quiet or self.state is not None: self.state=None; self.redraw()
            return
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
        if self.feature_off(): self.draw_feature_off()
        else: self.draw(self.state)
        if top and scroll is not None:   # rows drawn again (a dialog open over the page, say) stay where they were
            GLib.idle_add(lambda:(scroll.get_vadjustment().set_value(top),GLib.SOURCE_REMOVE)[1]); self.subtitle.set_text(self.status or self.summary())
        for widget_ref in ("_return_focus",):   # a dialog open over this page goes back to the row's new button
            w=getattr(self.win,widget_ref,None)
            if w is not None and id(w) in stale and stale[id(w)] in self._ids: setattr(self.win,widget_ref,self._ids[stale[id(w)]])
        last=self.win._last_page_focus.get(self.key)
        if last is not None and id(last) in stale and stale[id(last)] in self._ids: self.win._last_page_focus[self.key]=self._ids[stale[id(last)]]
        ident=getattr(self,"focus_ident",None)
        if ident is not None and old is None and self._ids.get(ident) is not None:
            self.focus_ident=None; GLib.idle_add(lambda w=self._ids[ident]:(usable(w) and w.grab_focus(),GLib.SOURCE_REMOVE)[1])
        if old is not None:
            target=self._ids.get(old) or (next((w for i,w in self._ids.items() if i.startswith(old)),None) if old==wanted else None)
            if target is not None and usable(target): target.grab_focus()
            elif not self.win._focus_first(self.groups): self.win.tab_buttons[self.key].grab_focus()
    def draw(self, state): pass
    def draw_feature_off(self):
        f=features.BY_KEY[features.PAGE_FEATURE[self.key]]
        self.section("NOT INSTALLED")
        self.note(f"{f.what} It needs software that is not installed yet.")
        self.row(f"Install {f.label}","",lambda:install_feature(self,f),icon="list-add-symbolic",fallback="+",ident="feature:on",
                 detail=f"Installs {', '.join(f.packages)}. It asks for your password.")

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

    def row(self, label, value="", on_activate=None, detail="", icon=None, fallback="", ident=None, extras=(), value_css="setting-value", swatch=None, indent=0):
        """One row: an optional icon, its name (and a detail line under it), its value on the right (after a square of
        the colour `swatch`); square extra buttons follow it on the same row. ← / → move between them. `indent` (px)
        sets it in under the row before it, as a partition under its drive."""
        line=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(4))
        if indent: line.set_margin_start(S(indent))
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
        if swatch: inner.append(colour_swatch(swatch))
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

# ====================================================================== Appearance (TVWCS's own)
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

class _ConfigPage(Page):
    """A page of TVWCS's own options. Each change is saved to TVWCS's config file, read fresh first so nothing TVWCS
    saved meanwhile is lost, and the running TVWCS is asked to read it again; so is this Settings window."""
    refreshable=False
    def read(self): return ConfigStore()
    def summary(self): return f"TVWCS {__version__}"
    def change(self, edit, notice=""):
        """edit(store) changes a freshly read store; it is saved, and TVWCS reads it again."""
        store=ConfigStore(); edit(store); store.save(); self.state=store; self.redraw()
        tell_tvwcs("reload"); self.win.settings_changed(store.settings)
        if notice: self.win.notice(self.title,notice)
    def toggle(self, key):
        def edit(store): store.settings[key]=not store.settings[key]
        return lambda:self.change(edit)
    def option(self, label, key, hint="", invert=False):
        on=bool(self.state.settings[key])!=invert
        self.row(label,_on_off(on),self.toggle(key),ident=f"opt:{key}")
        if hint: self.note(hint)
    def note(self, text, css=None):
        l=super().note(text,css); l.set_margin_bottom(S(6)); return l

class AppearancePage(_ConfigPage):
    """How TVWCS looks (size, colours) and the few choices left in 4.0: closing when it loses focus and the screen edge
    margin. What depends on the mode is fixed: in TV mode (a TVWCS session) apps open in a workspace of their own, the
    pointer hides after 3 seconds, the bar is off and the Quick Menu stays open; in desktop mode none of that changes
    the desktop. Hotkeys have their own page, the application to open at login is on User, and TVWCS's own updates are
    on Software updates."""
    key="appearance"; title="Appearance"; icon="preferences-desktop-appearance-symbolic"; fallback="◐"

    def draw(self, store):
        st=store.settings
        self.section("LOOK")
        has_4k=self.has_4k(); tv=tv_mode(); size=st["scale"] or ""
        label=SCALE_LABELS.get(size) or f"Automatic ({SCALE_LABELS[scale_key(st,tv)]})"
        self.row("Interface size",label,lambda:self.win.choose_option("Interface size",scale_choices(size,has_4k,tv),size,self.pick_scale),ident="opt:scale")
        self.note("Automatic is TV Mode in a TVWCS session and Desktop otherwise"+("; 4K TV Mode suits a 4K TV." if has_4k else ". 4K TV Mode is offered when a 4K display is connected."))
        self.row("Theme",THEMES[st["theme"]],self.choose_theme,ident="opt:theme")
        self.note("Dark or light, for TVWCS and Settings. Applications that follow the desktop's colour scheme (most GTK apps, "
                  "and Flatpak apps and browsers through the desktop portal) switch with it.")
        self.row("Accent colour",accent_name(st["accent"]),self.choose_accent,ident="opt:accent",swatch=st["accent"])
        self.row("Background colour","",self.choose_wallpaper,ident="opt:wallpaper",swatch=st["wallpaper"])
        self.note("Shown where no application is open, and behind the Quick Menu.")

        self.section("BEHAVIOR")
        self.option("Close TVWCS when it loses focus","close_on_click_outside","Clicking another window, or another window opening, closes the Quick Menu.")
        self.row("Screen edge margin",f"{st['margin']} px",self.choose_margin,ident="opt:margin")
        self.note("Many TVs cut off the edges of the picture (overscan). This opens a full-screen preview: move the slider until the "
                  "Quick Menu and Applications are fully on screen.")

    # ---------------------------------------------------------- choices
    def has_4k(self):
        gd=Gdk.Display.get_default(); monitors=gd.get_monitors() if gd else None
        for i in range(monitors.get_n_items() if monitors is not None else 0):
            m=monitors.get_item(i); g=m.get_geometry(); f=max(1,m.get_scale_factor())
            if is_4k(g.width*f,g.height*f): return True
        return False
    def pick_scale(self, key): self.change(lambda s:s.settings.update(scale=key))   # settings_changed redraws Settings at it
    def choose_accent(self):
        current=self.state.settings["accent"].lower()
        options=[(c,accent_name(c)) for c in METRO_COLORS]+([] if current in METRO_COLORS else [(current,f"{current} (set in config.json)")])
        self.win.choose_option("Accent colour",options,current,lambda c:self.change(lambda s:s.settings.update(accent=c)),swatches=True)
    def choose_theme(self):
        self.win.choose_option("Theme",list(THEMES.items()),self.state.settings["theme"],lambda t:self.change(lambda s:s.settings.update(theme=t)))
    def choose_wallpaper(self):
        self.win.choose_swatch("Background colour","Six greys, six colours and the same colours darker.",WALLPAPERS,self.state.settings["wallpaper"],
                               lambda c:self.change(lambda s:s.settings.update(wallpaper=c)))
    def choose_margin(self):
        from tvwcs.ui_margin import MarginPreview
        st=self.state.settings
        def done(margin):
            if margin is not None and margin!=st["margin"]: self.change(lambda s:s.settings.update(margin=int(margin)))
            GLib.idle_add(lambda:(self._ids.get("opt:margin") is not None and self._ids["opt:margin"].grab_focus(),GLib.SOURCE_REMOVE)[1])
        MarginPreview(self.win,st["margin"],st["quick_width"],self.win.app.scale,st["accent"],done)

# ====================================================================== Remote and hotkeys
class HotkeysPage(_ConfigPage):
    """The keys that open the Quick Menu and Applications from a keyboard, a remote or a gamepad (TVWCS writes
    hotkeys.conf when it reads them again), and the apps that have a hotkey of their own."""
    key="hotkeys"; title="Remote and hotkeys"; icon="input-keyboard-symbolic"; fallback="⌨"
    def summary(self): return ""

    def draw(self, store):
        st=store.settings
        self.section("QUICK MENU HOTKEYS")
        for device in DEVICES:
            for name in DEVICE_ACTIONS[device]:
                self.row(DEVICE_LABELS[device],describe(st["hotkeys"][device][name]),lambda d=device,n=name:self.change_hotkey(store,d,n),ident=f"key:{device}:{name}")
        self.note("Keyboard: a modifier tapped on its own (such as Super) triggers when it is released, so Super combinations keep working. "
                  "Remote: most remotes send ordinary keys; F2 suits many of them. Gamepad: a mapper such as AntiMicroX turns its buttons into keys.")
        self.section("APPLICATION HOTKEYS")
        profiles=store.hotkey_profiles()
        if not profiles: self.note("No application has a hotkey. "+APP_HOTKEY_HINT)
        for p in profiles:
            remove=self.button("window-close-symbolic","✕",f"Remove the hotkey for {p.name}",lambda pid=p.id:self.change(lambda s:s.set_profile_hotkey(pid,"")),danger=True)
            self.row(p.name,describe(p.hotkey),lambda pid=p.id,name=p.name:self.change_app_hotkey(store,pid,name),ident=f"key:app:{p.id}",extras=[remove])
        if profiles: self.note(APP_HOTKEY_HINT)
        self.row("Reset all hotkeys","Defaults",self.reset_hotkeys,ident="key:reset",
                 detail="Keyboard: tap Super. Remote: F2. Gamepad: none. Removes every application hotkey")

    def change_hotkey(self, store, device, name):
        label=f"{DEVICE_LABELS[device]}: {ACTION_LABELS[name]}"
        self.win.assign_hotkey(store,("slot",device,name),label,lambda spec:self.change(lambda s:s.set_slot_hotkey(device,name,spec)))
    def change_app_hotkey(self, store, pid, name):
        self.win.assign_hotkey(store,("profile",pid),name,lambda spec:self.change(lambda s:s.set_profile_hotkey(pid,spec)))
    def reset_hotkeys(self):
        def edit(s):
            for device in DEVICES:
                for name in DEVICE_ACTIONS[device]: s.set_slot_hotkey(device,name,DEFAULT_HOTKEYS[device][name])
            for p in s.hotkey_profiles(): s.set_profile_hotkey(p.id,"")
        n=len(ConfigStore().hotkey_profiles())
        self.win.confirm("Reset all hotkeys?","The Quick Menu hotkeys go back to their defaults"+(f", and the {n} application hotkey{'s' if n!=1 else ''} are removed." if n else "."),
                         "Reset",lambda:self.change(edit))

APP_HOTKEY_HINT="Give an app a hotkey with ✎ Edit on it in Applications."

# ====================================================================== TVWCS's own updates (on the Software updates page)
class _SelfUpdate:
    """TVWCS updates: a newer release from GitHub, prereleases, and the way back to the latest release."""
    update_text=""; updating=False
    def draw_self_update(self):
        self.section("TVWCS UPDATES")
        self.row("Check for TVWCS updates",self.update_text or f"Version {__version__}",None if self.updating else self.check_updates,ident="opt:update",
                 icon="view-refresh-symbolic",fallback="⟳")
        self.note(f"Looks for a newer release of TVWCS on GitHub ({selfupdate.GITHUB_REPO}) and offers to install it.")
        pre=ConfigStore().settings["update_prereleases"]
        self.row("Include prereleases",_on_off(pre),self.toggle_prereleases,ident="opt:update_prereleases")
        self.note("Every change is released as a prerelease first, and marked as the latest release once it has been tested "
                  "on a TV computer. On: Check for TVWCS updates offers prereleases too.")
        self.row("Roll back to the latest release","",None if self.updating else self.roll_back,ident="opt:rollback")
        self.note("Installs the release marked latest, even when it is older than this version: the way back from a prerelease.")
    def toggle_prereleases(self):
        store=ConfigStore(); store.settings["update_prereleases"]=not store.settings["update_prereleases"]; store.save(); tell_tvwcs("reload"); self.redraw()
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
        """Download the release, install the packages it needs that are missing here (asked first), then install it."""
        self.updating=True; self.update_text="Downloading…"; self.redraw()
        def failed(exc): self.updating=False; self.update_text="Update failed"; self.redraw(); self.win.notice("TVWCS updates",f"The update failed: {exc}")
        def downloaded(result):
            folder,missing=result
            if not missing: self.install_downloaded(release,folder,target,moving,""); return
            listing="\n".join(f"• {packages}: {why}" for packages,why in missing)
            def cancel(): self.win.close_modal(); selfupdate.discard(folder); self.updating=False; self.update_text=""; self.redraw()
            def install_them():
                try: argv=selfupdate.install_packages_argv([p for p,_w in missing])
                except ValueError as exc: self.install_downloaded(release,folder,target,moving,str(exc)); return
                self.update_text="Installing packages…"; self.redraw(); lines=[]
                def after(code,tail):
                    problem="" if code==0 else ("\n".join(lines[-3:]) or tail or "apt-get did not finish.").strip()
                    self.install_downloaded(release,folder,target,moving,problem)
                self.win.run_as_root(argv,"Installing packages",lines.append,after)
            self.win.confirm(f"TVWCS {release.version} needs more packages",
                             f"These packages are not installed yet:\n{listing}\n\nInstall them first? It asks for your password. "
                             "Cancel stops the update.","Install and update",install_them,danger=False,back=cancel)
        def fetch():
            folder=selfupdate.download_release(release)
            return folder,selfupdate.missing_packages(folder)
        in_background(fetch,downloaded,failed)
    def install_downloaded(self, release, folder, target, moving, package_problem):
        self.updating=True; self.update_text="Installing…"; self.redraw()
        def done(_out):
            selfupdate.discard(folder)
            self.updating=False; self.update_text=f"Installed {release.version}"; self.redraw()
            restarted=tell_tvwcs(f"restart {target/'bin'/'tvwcs'}")
            note=f" Some packages could not be installed: {package_problem}" if package_problem else ""
            self.win.notice("TVWCS updated",f"TVWCS {release.version} is installed"+(" and has restarted." if restarted else ".")+
                            " Close Settings and open it again to use the new version."+note)
        def failed(exc): selfupdate.discard(folder); self.updating=False; self.update_text="Update failed"; self.redraw(); self.win.notice("TVWCS updates",f"The update failed: {exc}")
        in_background(lambda:selfupdate.install_downloaded(folder,target,migrate=moving),done,failed)

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
        if s.battery.present:
            b=s.battery
            self.section("BATTERY")
            self.row("Battery",f"{b.percent}%",None,detail="Running on the battery" if b.on_battery else "Plugged in",
                     icon="battery-symbolic",fallback="🔋",ident="bat:now")
            c=s.critical
            self.row("When the battery is nearly empty",power.CRITICAL_ACTIONS[c["action"]],self.choose_critical,
                     icon="battery-caution-symbolic",fallback="🪫",ident="bat:action",
                     detail="" if c["action"]=="nothing" else f"At {c['percent']}% or less, while not plugged in")
            if c["action"]!="nothing": self.row("Nearly empty means",f"{c['percent']}%",self.choose_critical_percent,ident="bat:percent",indent=44)
            self.idle_rows(s,s.settings,"idle","WHEN NOTHING IS TOUCHED, PLUGGED IN")
            self.idle_rows(s,s.battery_settings,"idle_battery","WHEN NOTHING IS TOUCHED, ON BATTERY")
        else: self.idle_rows(s,s.settings,"idle","WHEN NOTHING IS TOUCHED")
        times=s.settings; screen=times["screen_off"]
        self.note("Times count from the last key, remote button or mouse movement. Nothing happens while sound is playing, "
                  "or while an application keeps the computer awake.")
        st=ConfigStore().settings
        saver=features.BY_KEY["screensaver"]; tv=tv_mode()
        if s.session=="sway": pass   # the screen saver is a plain fullscreen window, which sway handles badly: hidden there for now
        elif not features.installed(saver):
            self.section("SCREEN SAVER")
            self.row("Install the screen saver","",lambda:install_feature(self,saver),icon="video-display-symbolic",fallback="▭",ident="saver:feature",
                     detail=f"Installs {', '.join(saver.packages)}")
        else:
            self.section("SCREEN SAVER")
            logo=st["screensaver_logo"]
            self.row("Logo",SCREENSAVER_LOGOS[logo],self.choose_logo,detail=st["screensaver_image"] if logo=="image" else "",ident="saver:logo")
            if tv:   # a desktop session's lock screen is its own
                lock_saver=features.BY_KEY["lock_saver"]; ready=features.installed(lock_saver)
                on_lock=bool(st["screensaver_on_lock"]) and ready
                why=("Any key or button shows the lock screen; after a minute without input, the screen saver comes back. "
                     "Once the screen has turned off, it stays off instead") if ready else f"Needs {', '.join(lock_saver.packages)}. Choose this to install it"
                action=self.toggle_saver_on_lock if ready else lambda:install_feature(self,lock_saver,after=self.saver_on_lock_on)
                self.row("Show it when the computer locks",_on_off(on_lock),action,detail=why,
                         icon="system-lock-screen-symbolic",fallback="🔒",ident="saver:lock",value_css="state-on" if on_lock else "setting-value")
            self.row("Preview","",lambda:self.preview_saver(),detail="Shows the screen saver now. Any key or the mouse ends it.",ident="saver:preview",
                     icon="media-playback-start-symbolic",fallback="▶")
            self.note("A logo drifts across a black screen and changes colour each time it bounces off an edge. "
                      "A picture of your own can be any PNG, JPEG or SVG.")
        self.section("LOCKING")
        self.note("In a TVWCS session, TVWCS's lock screen locks the computer: it says the TV is locked and asks for your password. "
                  "In another session, Lock uses that desktop's own screen locker." if tv else
                  "This is not a TVWCS session, so Lock uses this desktop's own screen locker, such as i3lock or swaylock. "
                  "TVWCS's lock screen is used in a TVWCS session.")
        if not s.idle_works and any(times[a] for a in power.ACTIONS):
            self.note("These times need swayidle on sway. Install it, then sign out and in again." if s.session=="sway" else
                      "TVWCS cannot tell how long the computer has been idle: install libxss1, or xprintidle.","error")
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
                         detail="xss-lock is running"+((", started by TVWCS's session config" if os.environ.get("TVWCS_SESSION") else ", started by your i3 config")+". Choose this to stop it" if s.xss_lock!="?" else
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
        self.note(("Change “Turn off the screen after” to let TVWCS decide instead of X. " if s.session=="X11" else "")+
                  "logind's settings are changed in /etc/systemd/logind.conf, as root.")

    def idle_rows(self, s, times, option, heading):
        """The four times of one set: "idle" (plugged in, or a computer without a battery) or "idle_battery"."""
        self.section(heading); tag="" if option=="idle" else "bat"
        if features.installed(features.BY_KEY["screensaver"]) and s.session!="sway":   # not on sway yet (see power.swayidle_argv)
            self.row(power.LABELS["screensaver"],power.duration_text(times["screensaver"]),lambda:self.choose("screensaver",times["screensaver"],option=option),
                     icon="video-display-symbolic",fallback="▭",ident=f"idle{tag}:screensaver")
        screen=times["screen_off"]
        self.row(power.LABELS["screen_off"],self.system_screen_text(s) if screen is None else power.duration_text(screen),
                 lambda:self.choose("screen_off",screen,system=True,option=option),icon="video-display-symbolic",fallback="🖵",ident=f"idle{tag}:screen_off")
        self.row(power.LABELS["lock"],power.duration_text(times["lock"]),lambda:self.choose("lock",times["lock"],option=option),
                 detail="" if s.locker else "No screen locker is installed (such as i3lock, or swaylock on sway)",
                 icon="system-lock-screen-symbolic",fallback="🔒",ident=f"idle{tag}:lock")
        self.row(power.LABELS["sleep"],power.duration_text(times["sleep"]),lambda:self.choose("sleep",times["sleep"],option=option),
                 detail="" if s.can_sleep else "Nothing on this computer can make it sleep",
                 icon="weather-clear-night-symbolic",fallback="☾",ident=f"idle{tag}:sleep")
    def choose_critical(self):
        def picked(key):
            store=ConfigStore(); store.settings["battery_critical"]["action"]=key; store.save(); tell_tvwcs("reload"); self.refresh(quiet=True)
        self.win.choose_option("When the battery is nearly empty",list(power.CRITICAL_ACTIONS.items()),self.state.critical["action"],picked)
    def choose_critical_percent(self):
        def picked(key):
            store=ConfigStore(); store.settings["battery_critical"]["percent"]=int(key); store.save(); tell_tvwcs("reload"); self.refresh(quiet=True)
        self.win.choose_option("Nearly empty means",[(str(p),f"{p}%") for p in power.CRITICAL_PERCENTS],str(self.state.critical["percent"]),picked)

    def choose_logo(self):
        def picked(key):
            if key=="image": self.ask_image(); return
            store=ConfigStore(); store.settings["screensaver_logo"]=key; store.save(); self.redraw()
        self.win.choose_option("Screen saver logo",list(SCREENSAVER_LOGOS.items()),ConfigStore().settings["screensaver_logo"],picked)
    def ask_image(self, error=""):
        def got(path):
            full=os.path.expanduser(path.strip())
            if not os.path.isfile(full): self.ask_image(f"There is no file at {path.strip() or '(nothing typed)'}."); return
            store=ConfigStore(); store.settings["screensaver_logo"]="image"; store.settings["screensaver_image"]=path.strip(); store.save(); self.redraw()
        self.win.ask_text("Your own logo","The picture's path, such as ~/Pictures/logo.png. A picture with a transparent background looks best.",got,
                          ConfigStore().settings["screensaver_image"] or "~/Pictures/",error=error)
    def preview_saver(self):
        from tvwcs.lockscreen import launcher
        from tvwcs import screensaver
        if screensaver.cairo_missing(): self.win.notice("Screen saver",screensaver.MISSING_CAIRO); return
        try: subprocess.Popen([launcher(),"screensaver","--preview"],start_new_session=True,stdin=subprocess.DEVNULL)
        except OSError as exc: self.win.notice("Screen saver",f"Could not start it: {exc}")
    def stop_xss_lock(self):
        path=self.state.xss_lock
        self.win.confirm("Stop locking when the screen turns off",
                         "xss-lock locks the screen every time it turns off, even with “Lock after” set to Never, so a TV wakes up "
                         f"to a password prompt. TVWCS will turn it off in {path.replace(str(Path.home()),'~',1)} (keeping a copy of the file as "
                         f"{os.path.basename(path)}.before-tvwcs) and stop it now. “Lock after” still locks when you choose a time.",
                         "Stop it",lambda:self.act(lambda:power.stop_xss_lock(path),"Stopping xss-lock…","Power and sleep"),danger=False)

    def toggle_saver_on_lock(self, on=None):
        store=ConfigStore(); on=not store.settings["screensaver_on_lock"] if on is None else on
        store.settings["screensaver_on_lock"]=on; store.save(); tell_tvwcs("reload")
        self.point_xss_lock(store.settings); self.redraw()
    def saver_on_lock_on(self): self.toggle_saver_on_lock(True)
    def point_xss_lock(self, settings):
        """xss-lock (locking when the screen turns off) locks the same way as Lock: through `tvwcs lock` when TVWCS's
        lock screen or the screen saver while locked is chosen, else with the locker it ran before."""
        path=getattr(self.state,"xss_lock","")
        if not path and self.state.session=="X11": path=power.i3_config_path() or ""   # its line is there even when it is not running now
        if path and path!="?":
            from tvwcs.lockscreen import launcher
            why=power.use_tvwcs_locker(path,f"{launcher()} lock --nofork" if tv_mode() else "")
            if why: self.win.notice("Lock screen",why)

    @staticmethod
    def system_screen_text(s):
        if s.session=="sway": return "Never (sway)"
        x=s.xtimers; t=min([v for v in (x.saver,x.dpms_off) if v] or [0])
        return f"{power.duration_text(t)} (X)" if t else "Never (X)"

    def choose(self, action, current, system=False, option="idle"):
        options=([("system","Let the system decide")] if system else [])+[(str(v),power.duration_text(v)) for v in power.CHOICES]
        def picked(key):
            value=None if key=="system" else int(key)
            store=ConfigStore(); store.settings[option][action]=value; store.save(); tell_tvwcs("reload")
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
        shown,unplugged=sound.split_unplugged(state.outputs,current.name if current else "")
        if current is None: self.note(self.no_output_text(state))
        else:
            self.volume_row(current,"out"); self.device_row(current,True,"audio-speakers-symbolic","🔈")
        others=[d for d in shown if current is None or d.name!=current.name]+unplugged
        self.unplugged_rows("out",[lambda d=d:self.device_row(d,False,"audio-speakers-symbolic","🔈") for d in others]
                            +[lambda o=o:self.card_output_row(o) for o in state.other_outputs])
        self.section("INPUT")
        current=state.input()
        shown,unplugged=sound.split_unplugged(state.inputs,current.name if current else "")
        if current is None: self.note("No microphone or other input is connected.")
        else:
            self.volume_row(current,"in"); self.device_row(current,True,"audio-input-microphone-symbolic","🎤")
        others=[d for d in shown if current is None or d.name!=current.name]+unplugged
        self.unplugged_rows("in",[lambda d=d:self.device_row(d,False,"audio-input-microphone-symbolic","🎤") for d in others])
        self.note("Choosing a device uses it from now on; sound that is already playing moves to it too.")
        self.section("VOLUME")
        boost=bool(ConfigStore().settings["audio_boost"])
        self.row("Allow over-amplification",_on_off(boost),self.toggle_boost,ident="sound:boost",value_css="state-on" if boost else "setting-value",
                 detail="Up to 150 %. Louder, but the sound can distort. Off, volumes stop at 100 %")

    def toggle_boost(self):
        store=ConfigStore(); store.settings["audio_boost"]=not store.settings["audio_boost"]; store.save(); tell_tvwcs("reload"); self.redraw()

    def unplugged_rows(self, kind, draws):
        """The inactive outputs or inputs (nothing plugged in, or another profile of the card), folded under one row,
        "3 inactive outputs", that opens and closes them: they can still be tried, but seldom are."""
        if not draws: return
        opened=getattr(self,"opened",set()); self.opened=opened; is_open=kind in opened
        def toggle():
            opened.symmetric_difference_update({kind}); self.redraw()
        what=("output" if kind=="out" else "input")+("s" if len(draws)!=1 else "")
        self.row(f"{len(draws)} inactive {what}","Hide" if is_open else "Show",toggle,
                 detail="Not in use now, but they can be tried",icon="pan-down-symbolic" if is_open else "pan-end-symbolic",
                 fallback="▾" if is_open else "▸",ident=f"unplugged:{kind}")
        if is_open:
            for draw in draws: draw()

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
        detail=f"{o.card_label} · switches the sound card to this output"
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
        boost=bool(ConfigStore().settings["audio_boost"])
        scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,sound.top(boost),1); scale.set_draw_value(False); scale.set_hexpand(True)
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
            in_background(lambda:sound.set_volume(d,level,boost),lambda r:applied(r,"change the volume of")); return GLib.SOURCE_REMOVE
        def step(direction):
            d.volume=sound.stepped(d.volume,direction,boost); show()
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
    """Resolution, refresh rate and scale of each display; with several, which are on, where each one is and (X11) the
    primary one. On X11 the scale is one for the session, with fractional scales behind a switch. A change that can
    leave a screen blank or unreadable goes back by itself unless it is kept."""
    key="displays"; title="Displays"; icon="video-display-symbolic"; fallback="🖵"; poll=5
    KEEP_SECONDS=15
    def read(self):
        s=display.read_state()
        if s.available:
            names=self.monitor_names()
            for o in s.outputs: o.label=o.label or names.get(o.name,"")
            if s.backend=="xrandr": s.tearing=display.read_tearing()
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
        x11=s.backend=="xrandr"
        if x11 and on:
            self.section("SCALE")
            now=display.session_scale(outs)
            self.scale_buttons("scale:all",display.scale_choices(outs,s.fractional,now,s.max_size),now,lambda v:self.change_all(display.scaled(outs,v),True),
                               "Makes text and controls bigger on every display")
            self.row("Fractional scaling",_on_off(s.fractional),self.toggle_fractional,
                     detail="Also offers 125 %, 150 %, 175 % and more. Those are a little less sharp, and use more of the graphics card",
                     ident="scale:fractional",value_css="state-on" if s.fractional else "setting-value")
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
            if not x11:
                self.scale_buttons(f"{o.name}:scale",display.scale_choices([o],True,o.scale),o.scale,lambda v,o=o:self.change(o,True,scale=v),
                                   "Makes text and controls bigger")
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
        t=getattr(s,"tearing",None)
        if x11 and t is not None and (t.kind or t.nvidia_settings):
            self.section("TEARING")
            if t.kind:
                name="Force full composition pipeline (NVIDIA)" if t.kind=="nvidia" else "TearFree (Xorg)"
                self.row("Tear-free video",_on_off(t.on),lambda:self.toggle_tearing(t),detail=name+". Stops lines where two frames meet in videos and games",
                         ident="tear:on",value_css="state-on" if t.on else "setting-value")
            if t.nvidia_settings:
                self.row("NVIDIA settings","",self.open_nvidia_settings,icon="preferences-desktop-display-symbolic",fallback="🖵",ident="tear:nvidia",
                         detail="Opens NVIDIA's own settings. It may need a mouse to use")
        notes=[f"A new resolution, refresh rate, scale or display switched on or off goes back after {self.KEEP_SECONDS} seconds unless you keep it, "
               "in case a display cannot show it."]
        if x11: notes.append("Some open apps use a new scale only once they are started again, and window titles at the next log-in.")
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

    def toggle_tearing(self, t):
        on=not t.on
        def work():
            problem=display.set_tearing(t,on)
            if not problem: display.save_tearing(on)
            return problem
        self.act(work,"Changing tear-free video…","Displays")
    def open_nvidia_settings(self):
        def go():
            try: subprocess.Popen(["nvidia-settings"],start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            except OSError as exc: self.win.notice("NVIDIA settings",f"Could not open it: {exc}")
        self.win.confirm("Open NVIDIA settings?","NVIDIA's settings app is made for a mouse and keyboard: a remote may not be able to use it.",
                         "Open",go,danger=False)
    def scale_buttons(self, ident, choices, current, pick, detail):
        """Scale: one button per scale (75 % to 200 %), the one in use marked."""
        head=Gtk.Label(label="Scale"); head.set_xalign(0); head.set_margin_top(S(6)); self.add(head)
        line=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(4)); line.set_homogeneous(True); buttons=[]
        for v in choices:
            b=Gtk.Button(label=display.scale_text(v))
            if current is not None and abs(v-current)<0.005: b.add_css_class("active")
            else: b.connect("clicked",lambda _b,v=v:pick(v))
            line.append(b); buttons.append(b)
        self.add(line); self.register(*buttons,ident=ident); self.note(detail)

    # ---------------------------------------------------------- choosing
    def choose_mode(self, o):
        mode=o.mode()
        self.win.choose_option(f"Resolution · {o.title}",[(m.key,display.mode_text(m)+(" (recommended)" if m.preferred else "")) for m in o.modes],
                               mode.key if mode else None,lambda key:self.change(o,True,mode=key))
    def choose_scale(self, o):
        """sway: any scale, display by display."""
        self.win.choose_option(f"Scale · {o.title}",[(v,display.scale_text(v)) for v in display.scale_choices([o],True,o.scale)],
                               o.scale,lambda v:self.change(o,True,scale=v))
    def choose_session_scale(self):
        outs=self.state.outputs; now=display.session_scale(outs)
        self.win.choose_option("Scale",[(v,display.scale_text(v)) for v in display.scale_choices(outs,self.state.fractional,now,self.state.max_size)],now,
                               lambda v:self.change_all(display.scaled(outs,v),True))
    def toggle_fractional(self):
        on=not self.state.fractional
        try: display.set_fractional(on)
        except OSError as exc: self.win.notice("Displays",f"Could not save the choice: {exc}"); return
        now=display.session_scale(self.state.outputs)
        if not on and not display.is_whole(now):   # back to a whole step: the nearest one
            self.change_all(display.scaled(self.state.outputs,float(max(1,math.floor(now+0.5)))),True)
        else: self.refresh(quiet=True)
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
        self.change_all(display.edited(self.state.outputs,o.name,**changes),risky)
    def change_all(self, new, risky):
        s=self.state; old=s.outputs
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

class UpdatesPage(_SelfUpdate, _Console, Page):
    """TVWCS's own updates, then the system's packages and Flatpak apps."""
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
        if self.running:
            self.row(self.running,"Working…",None,icon="emblem-synchronizing-symbolic",fallback="⟳",ident="running")
            self.note("Leave this running until it finishes. Settings can be closed; the update carries on.")
            self.add(self.console()); return
        self.draw_self_update()
        self.section("SYSTEM AND APPS")
        if not s.available: self.note(s.message); return
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
            self.refresh(); tell_tvwcs("status")   # the Quick Menu's updates icon counts again
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
        self.run_steps(f"Installing {a.name}",steps,f"{a.name} is installed. Open it here, or from Applications.",a.id)
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
        if s.passwords and s.active and ConfigStore().settings["password_keyboard"]=="digits":
            self.note("Your password keyboard is the number pad, so your password may be only digits, which is easy to guess. "
                      "Keys only is recommended: then nobody can sign in over the network with a password.","error")
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
        if not s.unit: self.win.notice("SSH","The SSH server has no systemd service here (ssh), so Settings cannot start or stop it."); return
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
        if not s.managed or wireless[0].state.startswith("unmanaged"):
            for i in wireless: self.ethernet_row(i,s.managed)
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
        go=None; extras=[]; detail=self._details(i)
        if managed and i.state.startswith("unmanaged"):
            go=lambda i=i:self.take_over(i)
            detail=" · ".join(x for x in ("Not set up through NetworkManager, so it cannot be changed here. Choose it to let Settings manage it",detail) if x)
        elif managed and i.state not in ("unavailable",):
            if i.connected:
                go=lambda i=i:self.win.confirm(f"Disconnect {i.device}?",f"Disconnect {i.connection or i.device}? Anything using the network will lose it until you connect again.",
                                               "Disconnect",lambda:self.act(lambda:network.disconnect_device(i.device),f"Disconnecting {i.device}…","Ethernet"))
            else: go=lambda i=i:self.act(lambda:network.connect_device(i.device),f"Connecting {i.device}…","Ethernet")
        label=("Ethernet" if i.kind=="ethernet" else "Wi-Fi")+f" ({i.device})"
        self.row(label,self._state_text(i),go,detail=detail,icon="network-wired-symbolic" if i.kind=="ethernet" else "network-wireless-symbolic",
                 fallback="⇄",ident=f"if:{i.device}",extras=extras,value_css="state-on" if i.connected else "setting-value")
        if managed: self.ip_row(i)

    def take_over(self, i):
        """Hand a port that NetworkManager leaves alone to it (control_network: with ifupdown, a minimal Debian
        install's network, ifupdown is uninstalled)."""
        reason=network.unmanaged_reason(i.device); kind="Wi-Fi" if i.kind=="wifi" else "Ethernet"
        if reason=="ifupdown":
            text=(f"{i.device} is set up by ifupdown (/etc/network/interfaces), as a minimal Debian install does, and NetworkManager (which "
                  "Settings uses) will not touch it. Settings can hand the network to NetworkManager: ifupdown is uninstalled, /etc/network "
                  "is removed and NetworkManager is restarted, so it manages every Ethernet port and Wi-Fi adapter from then on.\n\n"
                  "The network drops for a moment. Ethernet connects again by itself, but you have to choose your Wi-Fi network and enter "
                  "its password again here, and any IP address, gateway or DNS servers set by hand have to be set again. It asks for your password.")
            title,ok="Hand the network to NetworkManager?","Hand it over"
        else:
            text=(f"NetworkManager is set to leave {i.device} alone. Settings can ask it to manage it. "
                  "If that does not last after a restart, a file in /etc/NetworkManager/conf.d lists it under unmanaged-devices.")
            title,ok=f"Manage {i.device} here?","Manage it"
        def go():
            self.set_status(f"Handing {i.device} to NetworkManager…"); lines=[]
            def done(code,tail):
                self.set_status("")
                if code: self.win.notice(kind,("\n".join(lines[-6:]) or tail or "It did not work.").strip())
                else: self.win.notice(kind,"NetworkManager manages the network now."+(" Choose your Wi-Fi network to connect again."
                                      if any(w.kind=="wifi" for w in self.state.interfaces) and reason=="ifupdown" else ""))
                self.refresh(quiet=True)
            self.win.run_as_root(network.take_over_argv(i.device,reason),f"Handing {i.device} to NetworkManager",lines.append,done)
        self.win.confirm(title,text,ok,go,danger=reason=="ifupdown")

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

# ====================================================================== Storage
class StoragePage(Page):
    """The drives in the computer and plugged into it (open, close, switch off before unplugging), and network shares
    (connect, disconnect, add, forget). See control_storage."""
    key="storage"; title="Storage"; icon="drive-harddisk-symbolic"; fallback="🖴"; poll=5
    def read(self): return storage.read_state(ConfigStore().settings["network_shares"])
    def summary(self):
        s=self.state
        return f"{len(s.drives)} drive{'s' if len(s.drives)!=1 else ''}" if s else ""
    def draw(self, s):
        self.section("DRIVES")
        if s.message: self.note(s.message,"error")
        if not s.drives: self.note("No drives were found.")
        for d in s.drives: self.drive_rows(d,s)
        if not s.udisks: self.note("Install udisks2 to open and close drives here.","error")
        self.note("Each drive's partitions are listed under it. Mounting a partition makes its files readable, in the folder shown "
                  "under it. Unmount it, or switch the drive off with ⏏, before unplugging it.")
        self.section("NETWORK SHARES")
        if not features.installed(features.BY_KEY["samba"]):
            self.row("Install network shares","",lambda:install_feature(self,features.BY_KEY["samba"]),icon="folder-remote-symbolic",fallback="⇄",
                     ident="share:feature",detail="To connect to Windows, Samba, NFS or SSH shares. Installs "+", ".join(features.BY_KEY["samba"].packages))
            return
        missing=[p for p,ok in (("libglib2.0-bin (the gio command)",s.gio),("gvfs-backends",s.smb)) if not ok]
        if missing: self.note("Connecting to network shares needs "+" and ".join(missing)+". Install it with sudo apt install "
                              +" ".join(m.split()[0] for m in missing)+".","error")
        for sh in s.shares: self.share_row(sh,s)
        if not s.shares: self.note("No network shares yet.")
        self.row("Add a network share","",self.add_share if s.gio else None,icon="list-add-symbolic",fallback="+",ident="share:add",
                 detail="A folder shared by another computer or a NAS, such as smb://nas/videos")
        self.note("Shares from Windows or Samba start with smb://, NFS with nfs://, SSH with sftp://. Their files appear in "
                  f"/run/user/{os.getuid()}/gvfs/ and in file managers. Passwords are not stored by TVWCS.")

    def drive_rows(self, d, s):
        kind="Inside the computer" if not d.removable else ("USB drive" if d.transport=="usb" else "Removable drive")
        extras=[]
        if d.removable and not d.system and s.udisks:
            extras.append(self.button("media-eject-symbolic","⏏",f"Switch off {d.title} so it can be unplugged",lambda d=d:self.eject(d)))
        self.row(d.title,storage.size_text(d.size),None,detail=kind+(" · holds this system" if d.system else ""),icon="drive-removable-media-symbolic" if d.removable else "drive-harddisk-symbolic",
                 fallback="🖴",ident=f"drive:{d.name}",extras=extras)
        for v in d.volumes:
            if v.fstype=="swap": continue
            space=f"{storage.size_text(v.used)} used, {storage.size_text(v.avail)} free" if v.mounted and (v.used or v.avail) else storage.size_text(v.size)
            where=", ".join(v.mountpoints)
            go=None
            if v.system:   # /, /home, /boot...: always in use, never unmounted from here
                value,detail="Part of the system",f"Always in use · its files are in {where}" if where else "Always in use"
            elif v.mounted:
                value,detail="Mounted",f"Its files are in {where}"
            else:
                value,detail="Not mounted","Mount it to see its files"
            if not v.system and s.udisks and v.fstype not in ("crypto_LUKS","LVM2_member"):
                go=(lambda v=v:self.act(lambda:storage.unmount(v.path),f"Unmounting {v.title}…","Storage")) if v.mounted else \
                   (lambda v=v:self.act(lambda:storage.mount(v.path),f"Mounting {v.title}…","Storage"))
                if not v.mounted: detail="Select to mount it and see its files"
                else: detail+=" · select to unmount"
            detail=" · ".join(x for x in (v.fstype,detail,space) if x)
            self.row(v.title,value,go,detail=detail,ident=f"vol:{v.name}",indent=44,
                     value_css="state-on" if v.mounted and not v.system else "setting-value")

    def eject(self, d):
        def work():
            for v in d.volumes:
                if v.mounted:
                    problem=storage.unmount(v.path)
                    if problem: return problem
            return storage.power_off(d.path)
        self.act(work,f"Switching off {d.title}…","Storage",after=lambda:None)

    def share_row(self, sh, s):
        forget=self.button("user-trash-symbolic","✕",f"Forget {sh.address}",lambda sh=sh:self.win.confirm("Forget this share?",
                           f"Remove {storage.share_label(sh.address)} from the list"+(" and disconnect it?" if sh.connected else "?"),"Forget",lambda:self.forget(sh)),danger=True)
        go=(lambda sh=sh:self.act(lambda:storage.disconnect(sh.address),"Disconnecting…","Network share")) if sh.connected else (lambda sh=sh:self.connect(sh.address))
        self.row(storage.share_label(sh.address),"Connected" if sh.connected else "Not connected",go if s.gio else None,
                 detail=sh.path if sh.connected else sh.address,icon="folder-remote-symbolic",fallback="⇄",ident=f"share:{sh.address}",
                 extras=[forget],value_css="state-on" if sh.connected else "setting-value")

    def add_share(self, error="", initial="smb://"):
        def got(address):
            address=address.strip(); problem=storage.valid_address(address)
            if problem: self.add_share(problem,address); return
            store=ConfigStore()
            if not any(storage.same_share(address,x) for x in store.settings["network_shares"]): store.settings["network_shares"].append(address); store.save()
            self.connect(address)
        self.win.ask_text("Add a network share","The share's address, such as smb://nas/videos or smb://192.168.0.10/music.",got,initial,ok_label="Next",error=error)
    def connect(self, address):
        def with_user(user):
            if not user.strip():
                self.act(lambda:storage.connect(address),f"Connecting to {storage.share_label(address)}…","Network share"); return
            self.win.ask_text("Password",f"The password for {user.strip()} on {urlparse_host(address)}. It is used to connect and not stored by TVWCS.",
                              lambda pw:self.act(lambda:storage.connect(address,user.strip(),pw),f"Connecting to {storage.share_label(address)}…","Network share"),
                              secret=True,ok_label="Connect")
        self.win.ask_text("User name",f"Your user name on {urlparse_host(address)}. Leave it empty to connect as a guest.",with_user,"",ok_label="Next")
    def forget(self, sh):
        def work():
            problem=storage.disconnect(sh.address) if sh.connected else ""
            store=ConfigStore(); store.settings["network_shares"]=[x for x in store.settings["network_shares"] if not storage.same_share(x,sh.address)]; store.save()
            return problem
        self.act(work,"Forgetting the share…","Network share")

def urlparse_host(address):
    from urllib.parse import urlparse
    return urlparse(address).hostname or address

# ====================================================================== Date and time
class DateTimePage(Page):
    """The time zone (a region, then a city), the clock set from the network, and the Quick Menu's 12/24-hour clock."""
    key="datetime"; title="Date and time"; icon="preferences-system-time-symbolic"; fallback="🕓"; poll=20
    def read(self): return timedate.read_state(),ConfigStore().settings["clock_24h"]
    def summary(self):
        return timedate.zone_label(self.state[0].timezone) if self.state else ""
    def draw(self, state):
        s,hours24=state; now=time.time()
        self.section("NOW")
        self.row("Time",timedate.clock_text(now,hours24),None,detail=timedate.date_text(now),icon="preferences-system-time-symbolic",fallback="🕓",ident="dt:now")
        self.section("TIME ZONE")
        region,city=timedate.split_zone(s.timezone)
        self.row("Region",region,self.choose_region,ident="dt:region")
        self.row("City",city,lambda:self.choose_city(region),ident="dt:city")
        self.note("Choosing a city sets the time zone for the whole computer. It may ask for your password.")
        self.section("NETWORK TIME")
        if s.timedatectl:
            self.row("Set the time from the network",_on_off(s.ntp),self.switch_ntp,
                     detail=("Synchronized" if s.synced else "Not synchronized yet") if s.ntp else
                            ("Turn it on to keep the clock right by itself" if s.can_ntp else "No network time service is installed (such as systemd-timesyncd or chrony)"),
                     ident="dt:ntp",value_css="state-on" if s.ntp else "setting-value")
        else: self.row("Set the time from the network","Unknown",None,detail="Needs systemd's timedatectl",ident="dt:ntp")
        self.section("SET THE TIME BY HAND")
        self.row("Set the time",timedate.clock_text(now,hours24),self.set_by_hand if s.timedatectl else None,
                 detail=("Turns network time off first" if s.ntp else "The date and the time of day") if s.timedatectl else "Needs systemd's timedatectl",ident="dt:set")
        self.section("QUICK MENU CLOCK")
        self.row("Clock",'24-hour (14:05)' if hours24 else "12-hour (2:05 PM)",self.choose_clock,ident="dt:clock")
        self.note("How the time at the bottom of the Quick Menu is written.")

    def as_root_if_needed(self, argv, label, status, after=None):
        """timedatectl as the user first (polkit may allow it), then as root when polkit wants a password.
        after() runs when it worked."""
        self.set_status(status); lines=[]
        def finish(code, tail):
            self.set_status("")
            if code: self.win.notice("Date and time",("\n".join(lines[-6:]) or tail or f"{label} did not work.").strip())
            elif after: after()
            self.refresh(quiet=True)
        def first(code, tail):
            if code and (argv[0]!="timedatectl" or privilege.polkit_refused(tail)): self.win.run_as_root(argv,label,lines.append,finish)
            else: finish(code,tail)
        if argv[0]=="timedatectl": StreamedRun(argv,lambda _l:None,first)
        else: self.win.run_as_root(argv,label,lines.append,finish)
    def switch_ntp(self):
        s=self.state[0]
        if not s.ntp and not s.can_ntp:
            self.win.notice("Network time","Install a network time service first, such as systemd-timesyncd (or chrony), with your package manager."); return
        self.focus_after="dt:ntp"
        self.as_root_if_needed(timedate.ntp_argv(not s.ntp),"Network time","Turning network time "+("off…" if s.ntp else "on…"))
    def choose_region(self):
        s=self.state[0]; groups=timedate.regions(s.zones); current,_city=timedate.split_zone(s.timezone)
        if not groups: self.win.notice("Time zone","No time zones were found on this computer (/usr/share/zoneinfo is empty)."); return
        self.win.choose_option("Region",[(r,f"{r}  ·  {len(c)} cit{'ies' if len(c)!=1 else 'y'}") for r,c in groups.items()],current,
                               lambda r:GLib.idle_add(lambda:(self.choose_city(r),GLib.SOURCE_REMOVE)[1]))
    def choose_city(self, region):
        s=self.state[0]; cities=timedate.regions(s.zones).get(region,[])
        if not cities: self.choose_region(); return
        def picked(zone):
            if zone==s.timezone or not timedate.valid_zone(zone,s.zones): return
            self.as_root_if_needed(timedate.timezone_argv(zone,s.timedatectl),"Time zone",f"Setting the time zone to {timedate.zone_label(zone)}…")
        self.win.choose_option(f"City · {region}",cities,s.timezone if s.timezone in dict(cities) else None,picked)
    # ---------------------------------------------------------- setting the time by hand
    def set_by_hand(self):
        s=self.state[0]
        if s.ntp:
            self.win.confirm("Turn network time off?","The time can only be set by hand while it is not set from the network. "
                             "Turn network time off now? You can turn it on again here.","Turn off",
                             lambda:self.as_root_if_needed(timedate.ntp_argv(False),"Network time","Turning network time off…",after=self.set_by_hand_now),danger=False)
            return
        self.set_by_hand_now()
    def set_by_hand_now(self):
        import datetime
        self.time_fields(datetime.datetime.now().replace(second=0,microsecond=0))
    def apply_time(self, when):
        self.win.close_modal()
        self.as_root_if_needed(timedate.set_time_argv(when),"Set the time",f"Setting the time to {when:%H:%M}…")
    def time_fields(self, when):
        """A box for each of year, month, day, hour and minute (typed in, or changed with the ▲ and ▼ above and below
        it), hour:minute, and AM/PM with the 12-hour clock. ← → move between the boxes, ↑ ↓ to the ▲ and ▼ rows."""
        win=self.win; win._begin_modal("Set the time"); hours24=self.state[1]
        state={"when":when,"pm":timedate.hour_12(when.hour)[1]}
        error=win._message("","error"); error.set_visible(False)
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(8)); row.set_halign(Gtk.Align.CENTER)
        ups=[]; downs=[]; entries={}; boxes=[]
        names={"year":"Year","month":"Month","day":"Day","hour":"Hour","minute":"Minute"}
        def show():
            w=state["when"]
            for f,e in entries.items():
                v=getattr(w,f)
                if f=="hour" and not hours24: v=timedate.hour_12(v)[0]
                e.set_text(f"{v:04d}" if f=="year" else f"{v:02d}")
            if not hours24: style_ampm()
        def typed():
            """The boxes as a time, or raises ValueError."""
            return timedate.from_fields(*(entries[f].get_text() for f in timedate.FIELDS),pm=None if hours24 else state["pm"])
        def move(field,delta):
            try: state["when"]=typed()
            except ValueError: pass   # a box being typed in: move from the last good time
            state["when"]=timedate.adjust(state["when"],field,delta)
            if field=="hour": state["pm"]=state["when"].hour>=12
            error.set_visible(False); show()
        def column(field):
            col=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4))
            up=Gtk.Button(label="▲"); up.connect("clicked",lambda _b:move(field,1)); col.append(up); ups.append(up)
            e=Gtk.Entry(); e.add_css_class("time-field"); e.set_alignment(0.5); e.set_max_length(4 if field=="year" else 2)
            e.set_width_chars(4 if field=="year" else 2); e.set_max_width_chars(4 if field=="year" else 2); e.set_input_purpose(Gtk.InputPurpose.DIGITS)
            e.connect("activate",lambda *_:submit()); entries[field]=e; boxes.append(e); col.append(e)
            down=Gtk.Button(label="▼"); down.connect("clicked",lambda _b:move(field,-1)); col.append(down); downs.append(down)
            n=Gtk.Label(label=names[field]); n.add_css_class("muted"); col.append(n); return col
        for field in ("year","month","day"): row.append(column(field))
        gap=Gtk.Box(); gap.set_size_request(S(18),-1); row.append(gap)
        row.append(column("hour"))
        colon=Gtk.Label(label=":"); colon.add_css_class("time-colon"); colon.set_valign(Gtk.Align.CENTER); row.append(colon)
        row.append(column("minute"))
        ampm=None
        if not hours24:   # one button: the current half of the day stands out, the other is dimmed
            ampm=Gtk.Button(); ampm.add_css_class("ampm"); ampm.set_valign(Gtk.Align.CENTER)
            pair=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(2)); am=Gtk.Label(label="AM"); pm=Gtk.Label(label="PM")
            pair.append(am); pair.append(pm); ampm.set_child(pair); ampm.set_tooltip_text("Switch between AM and PM")
            def style_ampm():
                for label,on in ((am,not state["pm"]),(pm,state["pm"])):
                    label.remove_css_class("ampm-on" if not on else "ampm-off"); label.add_css_class("ampm-on" if on else "ampm-off")
            def flip():
                try: state["when"]=typed()
                except ValueError: pass
                state["pm"]=not state["pm"]; state["when"]=state["when"].replace(hour=timedate.hour_24(timedate.hour_12(state["when"].hour)[0],state["pm"]))
                show()
            ampm.connect("clicked",lambda _b:flip()); row.append(ampm); boxes.append(ampm)
        win.modal_card.append(row)
        def submit():
            try: when=typed()
            except ValueError as exc: error.set_text(str(exc)); error.set_visible(True); return
            self.apply_time(when)
        for i,e in enumerate(boxes):   # ← → move between the boxes (in a box they would only move its cursor)
            keys=Gtk.EventControllerKey(); keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            def key(_c,keyval,_code,_state,i=i):
                if keyval not in (Gdk.KEY_Left,Gdk.KEY_Right): return False
                j=i+(1 if keyval==Gdk.KEY_Right else -1)
                if 0<=j<len(boxes): boxes[j].grab_focus()
                return True
            keys.connect("key-pressed",key); e.add_controller(keys)
            if isinstance(e,Gtk.Entry):
                focus=Gtk.EventControllerFocus(); focus.connect("enter",lambda _c,e=e:GLib.idle_add(lambda:(e.select_region(0,-1),GLib.SOURCE_REMOVE)[1])); e.add_controller(focus)
        show()
        cancel,ok=win._buttons(("Cancel",win.close_modal,None),("Set the time",submit,"active"))
        groups=[]
        for widgets in (ups,boxes,downs):
            g=NavGroup(widgets); g.column=True; groups.append(g)
        win._finish_modal(groups+[NavGroup([cancel,ok])],win.close_modal,entries["hour"])

    def choose_clock(self):
        def picked(key):
            store=ConfigStore(); store.settings["clock_24h"]=key=="24"; store.save(); tell_tvwcs("reload"); self.refresh(quiet=True)
        self.win.choose_option("Quick Menu clock",[("12","12-hour (2:05 PM)"),("24","24-hour (14:05)")],"24" if self.state[1] else "12",picked)

# ====================================================================== installing what a page needs
def install_feature(page, f, after=None):
    """Install the software a page needs (features.py), asking first; then the page reads again. after() runs once it is
    installed (Apps adds Flathub, say)."""
    def installed():
        tell_tvwcs("reload")
        if after: after()
        page.refresh(quiet=True)
    if features.installed(f): installed(); return
    missing=features.missing_packages(f) or list(f.packages)
    if not shutil.which("apt-get"):
        page.win.notice(f.label,f"{f.label} needs {', '.join(f.packages)} (the Debian names). Install them with your package manager.")
        return
    lines=[]
    def done(code, tail):
        page.set_status("")
        if code: page.win.notice(f.label,("\n".join(lines[-6:]) or tail or "The packages could not be installed.").strip()); return
        installed()
    def go():
        page.set_status(f"Installing {', '.join(missing)}…")
        page.win.run_as_root(features.install_argv(missing),f"Installing {f.label}",lines.append,done)
    page.win.confirm(f"Install {f.label}?",f"{f.what} It needs {', '.join(missing)}, which will be installed now. It asks for your password.",
                     "Install",go,danger=False)

# ====================================================================== User
class UserPage(Page):
    """This user's account (name, password) and logging in: the login screen in use and the automatic login."""
    key="user"; title="User"; icon="avatar-default-symbolic"; fallback="☺"
    def read(self): return login_ui.read_user()
    def summary(self): return login_ui.role(self.state[0]) if self.state else ""   # "Administrator" or "Standard User", small and grey beside "User"
    def draw(self, state): login_ui.draw_user(self,state)

PAGES=(AppearancePage,UserPage,HotkeysPage,SoundPage,DisplaysPage,PowerPage,BluetoothPage,DateTimePage,AppsPage,UpdatesPage,SystemPage,TerminalPage,NetworkPage,StoragePage)
