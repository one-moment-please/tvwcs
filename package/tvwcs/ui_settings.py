"""The Settings view of the Applications pane. Every row is one button, so it works with a D-pad:
Enter flips an On/Off toggle; a row with several choices opens a small pop-up listing them; other rows open a dialog."""
from __future__ import annotations
import threading
from pathlib import Path
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

from tvwcs import __version__, selfupdate
from tvwcs.hotkeys import DEFAULT_HOTKEYS, describe
from tvwcs.model import SCALE_LABELS, STARTUP_LABELS, STARTUP_MODES
from tvwcs.system_actions import SYSTEM_ACTIONS
from tvwcs.widgets import S, muted_label, section_title

def _on_off(flag): return "On" if flag else "Off"

def _in_background(work,done,failed):
    """Run work() on a worker thread (network and installs must not freeze the remote), then done(result) or
    failed(error) back on the GTK main loop."""
    def run():
        try: result=work()
        except Exception as exc: GLib.idle_add(lambda e=exc:(failed(e),GLib.SOURCE_REMOVE)[1]); return
        GLib.idle_add(lambda:(done(result),GLib.SOURCE_REMOVE)[1])
    threading.Thread(target=run,daemon=True).start()

def build_settings_panel(win, embedded=False):
    """The Settings tab. Every row is one button, so it works with a D-pad: Enter flips an On/Off toggle;
    a row with several choices opens a small pop-up listing them; other rows open a dialog.
    `embedded` keeps the pane inside the Applications window's tab bar instead of its own panel."""
    app=win.app; store=app.store; settings=store.settings; layout=app.layout
    nav="guide" if embedded else "options"   # embedded rows navigate with the Applications pane they live in
    pane=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0); pane.add_css_class("pane")
    if not embedded:
        pane.set_size_request(layout.quick_width,-1); pane.set_hexpand(False); pane.set_margin_start(layout.margin)
        title=Gtk.Label(label="Settings"); title.add_css_class("pane-title"); title.set_xalign(0)
        title.set_margin_top(S(14)); title.set_margin_start(S(20)); title.set_margin_bottom(S(10)); pane.append(title)
    scroll=Gtk.ScrolledWindow(); scroll.set_vexpand(True); scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC); pane.append(scroll)
    body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4)); body.set_margin_start(S(20)); body.set_margin_end(S(20)); body.set_margin_bottom(S(16)); scroll.set_child(body)
    # Two columns side by side (each a "lane": ←/→ jumps between them), then the System actions in a grid across both.
    columns=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(28)); columns.set_homogeneous(True); body.append(columns)
    lanes=[]
    for _ in range(2):
        column=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4)); columns.append(column); lanes.append(column)
    lane=[0]
    def put(widget): lanes[lane[0]].append(widget)

    def row(label,value,on_activate=None,hint=None):
        """One setting: its name on the left, its current value on the right. on_activate() may return the new value text."""
        b=Gtk.Button(); b.add_css_class("launch-row"); box=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(12))
        l=Gtk.Label(label=label); l.set_xalign(0); l.set_hexpand(True); l.set_wrap(True); box.append(l)
        v=Gtk.Label(label=value); v.add_css_class("setting-value"); v.set_xalign(1); v.set_wrap(True)
        if hasattr(v,"set_natural_wrap_mode"): v.set_natural_wrap_mode(Gtk.NaturalWrapMode.NONE)   # GTK 4.6+: wrap only if it truly does not fit
        box.append(v); b.set_child(box)
        def activate(*_):
            new=on_activate()
            if new is not None: v.set_text(new)
        b.connect("clicked",activate); put(b)
        group=win._register(nav,b)
        if group is not None: group.lane=lane[0]
        if hint: put(muted_label(hint))
        return v

    # ---- Display
    put(section_title("DISPLAY"))
    def pick_scale(key):
        settings["scale"]=key; store.save_settings(); app.apply_scale()   # rebuilds this panel
    row("Interface size",SCALE_LABELS[settings["scale"]],
        lambda:win.choose_option("Interface size",list(SCALE_LABELS.items()),settings["scale"],pick_scale),
        "Desktop for a monitor at arm's length; 10-foot for a TV across the room; 10-foot 4K for a 4K TV.")

    # ---- Behaviour
    put(section_title("BEHAVIOR"))
    def toggle(key):
        def go():
            settings[key]=not settings[key]; store.save_settings(); return _on_off(settings[key])
        return go
    row("Close when clicking outside",_on_off(settings["close_on_click_outside"]),toggle("close_on_click_outside"))
    row("Open running apps in a new workspace",_on_off(settings["open_in_new_workspace"]),toggle("open_in_new_workspace"),
        "On: selecting an open app gives it a workspace of its own. Off: it is tiled into the current workspace. Each app's options can open it the other way, and apps set to always launch in a new workspace are not affected.")
    row("Hide the options buttons in the Quick Menu",_on_off(settings["hide_options_buttons"]),toggle("hide_options_buttons"),
        "Even hidden, a row's options still open by pressing ← on it, or by right-clicking it.")
    row("Button hints",_on_off(settings["button_hints"]),toggle("button_hints"),
        "Shows what a button with only an icon does when it has been selected for 3 seconds, for 6 seconds.")

    # ---- Hotkeys (second column)
    lane[0]=1
    put(section_title("HOTKEYS"))
    labels={"menu":"Show / hide the Quick Menu","guide":"Open / close Applications"}; values={}
    def change(name):
        def got(spec):
            other="guide" if name=="menu" else "menu"
            if spec==settings["hotkeys"][other]: app.notify_message(f"{describe(spec)} is already used for “{labels[other]}”."); return
            app.set_hotkey(name,spec); values[name].set_text(describe(spec))
        return lambda:win.capture_hotkey(labels[name],got)
    for name in ("menu","guide"): values[name]=row(labels[name],describe(settings["hotkeys"][name]),change(name))
    def reset_keys():
        for name,spec in DEFAULT_HOTKEYS.items(): app.set_hotkey(name,spec); values[name].set_text(describe(spec))
    row("Reset hotkeys","Defaults",reset_keys,"Tapping Super (or another modifier) on its own works too, and Super combinations such as Super+Enter keep working. That needs xcape.")

    # ---- Start-up
    put(section_title("AT LOGIN"))
    names={p.id:p.name for p in store.profiles}
    def startup_label(): return STARTUP_LABELS[settings["startup"]["mode"]]
    def app_label():
        pid=settings["startup"]["profile_id"]; return names.get(pid,"Not chosen")
    def pick_startup(key):
        settings["startup"]["mode"]=key; store.save_settings(); mode_value.set_text(startup_label())
    mode_value=row("Open at login",startup_label(),
                   lambda:win.choose_option("Open at login",[(m,STARTUP_LABELS[m]) for m in STARTUP_MODES],settings["startup"]["mode"],pick_startup))
    app_value=None
    def choose():
        def picked(profile):
            settings["startup"].update(profile_id=profile.id,mode="app"); store.save_settings(); app_value.set_text(profile.name); mode_value.set_text(startup_label())
        win.choose_profile(picked)
    app_value=row("Chosen app",app_label(),choose,"“Reopen the last app” starts whichever app you used most recently. Either runs once per login, a moment after TVWCS starts.")

    # ---- Updates
    put(section_title("UPDATES"))
    busy=[False]; dest=selfupdate.install_dir(Path(selfupdate.__file__).parent)
    def update_failed(prefix):
        def failed(exc):
            busy[0]=False; update_value.set_text(prefix); app.notify_message(f"{prefix}: {exc}")
        return failed
    def install(release):
        busy[0]=True; update_value.set_text("Installing…")
        _in_background(lambda:selfupdate.install_release(release,dest),lambda _out:app.restart(),update_failed("Update failed"))
    def checked(release):
        busy[0]=False
        if not selfupdate.is_newer(release.version,__version__): update_value.set_text(f"Up to date ({__version__})"); return
        update_value.set_text(f"{release.version} available")
        if dest is None:
            app.notify_message(f"TVWCS {release.version} is available. This copy runs from a source checkout: update it with git pull."); return
        win.confirm("Update TVWCS?",f"TVWCS {release.version} is available (you have {__version__}). Download and install it now? "
                    "TVWCS restarts afterwards; your channels, favorites, settings and hotkeys are kept.","Install update",lambda:install(release))
    def check_updates():
        if busy[0]: return None
        busy[0]=True; _in_background(selfupdate.latest_release,checked,update_failed("Check failed")); return "Checking…"
    update_value=row("Check for updates",f"Version {__version__}",check_updates,
                     f"Looks for a newer release on GitHub ({selfupdate.GITHUB_REPO}) and offers to install it.")

    # ---- System: a grid across both columns; ↑/↓ keeps the column, ←/→ moves along a row
    body.append(section_title("SYSTEM"))
    grid=Gtk.Grid(); grid.set_column_spacing(S(4)); grid.set_row_spacing(S(4)); grid.set_column_homogeneous(True); body.append(grid)
    per_row=3; line=[]
    for i,action in enumerate(SYSTEM_ACTIONS):
        b=win.dialog_button(action.icon,action.fallback,action.label); b.set_hexpand(True); b.connect("clicked",lambda _b,a=action:win.system_action(a))
        grid.attach(b,i%per_row,i//per_row,1,1); line.append(b)
        if len(line)==per_row or i==len(SYSTEM_ACTIONS)-1:
            group=win._register(nav,*line)
            if group is not None: group.column=True
            line=[]
    return pane
