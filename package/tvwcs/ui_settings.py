"""The Settings panel (the third panel, right of the Channel Guide). Every row is one button, so it works with a D-pad:
Enter flips an On/Off toggle; a row with several choices opens a small pop-up listing them; other rows open a dialog."""
from __future__ import annotations
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from tvwcs.hotkeys import DEFAULT_HOTKEYS, describe
from tvwcs.model import SCALE_LABELS, STARTUP_LABELS, STARTUP_MODES
from tvwcs.system_actions import SYSTEM_ACTIONS
from tvwcs.widgets import S, muted_label, section_title

def _on_off(flag): return "On" if flag else "Off"

def build_settings_panel(win, embedded=False):
    """The Settings tab. Every row is one button, so it works with a D-pad: Enter flips an On/Off toggle;
    a row with several choices opens a small pop-up listing them; other rows open a dialog.
    `embedded` keeps the pane inside the Applications window's tab bar instead of its own panel."""
    app=win.app; store=app.store; settings=store.settings; layout=app.layout
    pane=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0); pane.add_css_class("pane")
    if not embedded:
        pane.set_size_request(layout.quick_width,-1); pane.set_hexpand(False); pane.set_margin_start(layout.margin)
        title=Gtk.Label(label="Settings"); title.add_css_class("pane-title"); title.set_xalign(0)
        title.set_margin_top(S(14)); title.set_margin_start(S(20)); title.set_margin_bottom(S(10)); pane.append(title)
    scroll=Gtk.ScrolledWindow(); scroll.set_vexpand(True); scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC); pane.append(scroll)
    content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4)); content.set_margin_start(S(20)); content.set_margin_end(S(20)); content.set_margin_bottom(S(16)); scroll.set_child(content)

    def row(label,value,on_activate=None,hint=None):
        """One setting: its name on the left, its current value on the right. on_activate() may return the new value text."""
        b=Gtk.Button(); b.add_css_class("launch-row"); box=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(12))
        l=Gtk.Label(label=label); l.set_xalign(0); l.set_hexpand(True); l.set_wrap(True); box.append(l)
        v=Gtk.Label(label=value); v.add_css_class("setting-value"); v.set_xalign(1); v.set_wrap(True); box.append(v); b.set_child(box)
        def activate(*_):
            new=on_activate()
            if new is not None: v.set_text(new)
        b.connect("clicked",activate); content.append(b); win._register("options",b)
        if hint: content.append(muted_label(hint))
        return v

    # ---- Display
    content.append(section_title("DISPLAY"))
    def pick_scale(key):
        settings["scale"]=key; store.save_settings(); app.apply_scale()   # rebuilds this panel
    row("Interface size",SCALE_LABELS[settings["scale"]],
        lambda:win.choose_option("Interface size",list(SCALE_LABELS.items()),settings["scale"],pick_scale),
        "Desktop for a monitor at arm's length; 10-foot for a TV across the room; 10-foot 4K for a 4K TV.")

    # ---- Behaviour
    content.append(section_title("BEHAVIOR"))
    def toggle(key):
        def go():
            settings[key]=not settings[key]; store.save_settings(); return _on_off(settings[key])
        return go
    row("Close when clicking outside",_on_off(settings["close_on_click_outside"]),toggle("close_on_click_outside"))
    row("Open running apps in a new workspace",_on_off(settings["open_in_new_workspace"]),toggle("open_in_new_workspace"),
        "On: selecting an open app gives it a workspace of its own. Off: it is tiled into the current workspace. Each app's options can open it the other way, and apps set to always launch in a new workspace are not affected.")
    row("Hide the options buttons in the Quick Menu",_on_off(settings["hide_options_buttons"]),toggle("hide_options_buttons"),
        "Reminder: even hidden, each row's options menu can still be opened by right-clicking the application or workspace, or by pressing ← while it is selected.")

    # ---- Hotkeys
    content.append(section_title("HOTKEYS"))
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
    content.append(section_title("AT LOGIN"))
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

    # ---- System
    content.append(section_title("SYSTEM"))
    for action in SYSTEM_ACTIONS:
        b=win.dialog_button(action.icon,action.fallback,action.label); b.connect("clicked",lambda _b,a=action:win.system_action(a))
        content.append(b); win._register("options",b)
    return pane
