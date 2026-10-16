"""The TVWCS window: Quick Menu | Applications, remote-friendly navigation and dialogs.
TVWCS's own options are a page of the Settings app (the Quick Menu's ⚙ opens it)."""
from __future__ import annotations
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk

from tvwcs import quick_status
from tvwcs.control_datetime import clock_text, date_text
from tvwcs.hotkeys import HotkeyCapture, describe, is_navigation
from tvwcs.model import LAUNCH_NEW_WORKSPACE, LAUNCH_SAME, MAIN_TITLE, extract_badge, profile_detail, row_description, search_items, startup_choices
from tvwcs.system_actions import power_menu
from tvwcs.theme import render_css
from tvwcs import cursor
from tvwcs.widgets import (NavGroup, PointerWatch, S, app_icon, child_marker, clear_box, glyph, held_modifiers, icon_button, icon_only, Marquee, muted_label, scroll_to_show, section_title, usable)

FOCUS_TIP_DELAY=3000                     # ms a selected icon-only button waits before showing its tooltip (Settings > Options > Button hints)
FOCUS_TIP_DURATION=6000                  # ms the tooltip then stays up
CHANNEL_DIGITS=3                         # typing this many digits of a channel number ...
CHANNEL_DELAY=1000                       # ... and nothing else for this many ms launches that channel

_TYPING_BLOCKED=Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.ALT_MASK|Gdk.ModifierType.SUPER_MASK|Gdk.ModifierType.META_MASK

class TVWCSWindow(Gtk.ApplicationWindow):
    """One borderless window holding two panels side by side. The Quick Menu is always there; the
    Applications pane opens to its right."""
    def __init__(self, app):
        super().__init__(application=app,title=MAIN_TITLE)
        self.app=app; self.guide_open=False; self.options_open=False
        self.guide_pane=None; self.options_pane=None; self.guide_scroll=None; self.guide_button=None; self.quick_content=None
        self.apps_title=None; self.apps_subtitle=None
        self._focus_tip=None; self._focus_tip_source=0; self._channel_source=0; self._capture_cancel=None
        self._provider=None; self._expanded={"Media","Internet","Games"}; self._guide_scroll=0.0
        self._popovers=0; self._was_active=False; self._capture=None; self._capture_cb=None; self._pin=None
        self._reset_nav()
        self.set_decorated(False); self.set_hide_on_close(True); self.set_resizable(True); self.add_css_class("tvwcs-window")
        self.pointer=PointerWatch(self,lambda:cursor.hide_ms(self.app.store.settings))   # hover colours only while the mouse is in use
        key=Gtk.EventControllerKey(); key.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key.connect("key-pressed",self._key_pressed); key.connect("key-released",self._key_released); self.add_controller(key)
        self.connect("notify::focus-widget",self._focus_changed); self.connect("notify::is-active",self._active_changed)
        self._build()

    def _reset_nav(self):
        self._groups={"quick":[],"guide":[],"options":[]}; self._header_group=[]
        self._search_results=[]; self._selected_result=0; self._result_groups=[]; self._result_mains=[]; self._stars={}
        self._modal_groups=[]; self._modal_back=None; self._return_focus=None; self._last_focus={}; self._pin=None; self._chan=None
        self._open_row=None; self._text=None
        self._descriptions=[]

    # ================================================================== construction
    def _build(self):
        if self.guide_scroll is not None: self._guide_scroll=self.guide_scroll.get_vadjustment().get_value()
        self._reset_nav(); self.guide_pane=None; self.options_pane=None; self.guide_scroll=None
        layout=self.app.layout
        self.set_child(None); self._install_css()
        overlay=Gtk.Overlay(); overlay.add_css_class("tvwcs-root")
        self.panes=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=0)
        self.quick_pane=self._build_quick_pane(layout.quick_width); self.panes.append(self.quick_pane)
        overlay.set_child(self.panes)
        self.modal_layer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL); self.modal_layer.add_css_class("modal-scrim")
        self.modal_reveal=Gtk.Revealer(); self.modal_reveal.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        self.modal_reveal.set_transition_duration(0 if self.app.store.settings.get("reduce_motion") else 120)
        self.modal_reveal.set_child(self.modal_layer); self.modal_reveal.set_can_target(False); self.modal_reveal.set_visible(False)
        self.modal_card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(6)); self.modal_card.add_css_class("modal-card")
        self.modal_card.set_halign(Gtk.Align.CENTER); self.modal_card.set_valign(Gtk.Align.CENTER); self.modal_card.set_hexpand(True); self.modal_card.set_vexpand(True)
        self._card_width=min(S(440),max(S(280),layout.quick_width-S(40))); self.modal_card.set_size_request(self._card_width,-1)
        self.modal_layer.append(self.modal_card); overlay.add_overlay(self.modal_reveal)
        self.set_child(overlay)
        self.set_panels(self.guide_open,self.options_open); self._refresh_search_results()

    def _install_css(self):
        display=Gdk.Display.get_default()
        if self._provider is None:
            self._provider=Gtk.CssProvider()
            if display: Gtk.StyleContext.add_provider_for_display(display,self._provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        settings=self.app.store.settings
        self._provider.load_from_data(render_css(settings["accent"],self.app.scale_factor,theme=settings.get("theme","dark")).encode("utf-8"))

    def set_panels(self,guide,options=None):
        """Show or hide the Applications pane, built once and kept, so closing and opening it again never disturbs
        scroll positions, open categories or focus. `options` is accepted for older callers but opens nothing."""
        guide=bool(guide)
        self.guide_open=guide; self.options_open=False
        if guide and self.guide_pane is None: self.guide_pane=self._build_guide_pane(); self.panes.append(self.guide_pane)
        layout=self.app.layout
        self.quick_pane.set_size_request(layout.quick_width,-1)
        if self.guide_pane is not None: self.guide_pane.set_visible(guide)
        if self.guide_button is not None:
            (self.guide_button.add_css_class if guide else self.guide_button.remove_css_class)("active")
            self.guide_button.set_tooltip_text("Hide Applications" if guide else "Open Applications (+)")

    def _build_quick_pane(self,width):
        pane=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0); pane.add_css_class("pane"); pane.set_size_request(width,-1); pane.set_hexpand(False)
        header=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(10)); header.set_margin_top(S(14)); header.set_margin_start(S(20)); header.set_margin_end(S(20)); header.set_margin_bottom(S(10))
        title=Gtk.Label(label="TVWCS"); title.add_css_class("brand"); title.set_xalign(0); title.set_hexpand(True); header.append(title)
        # ⚙ Settings, ⏻ the power menu, ✕ close (⚙ and ✕ can be hidden in Options), then the applications button,
        # whose right edge lines up with the search field. Focus order matches the left-to-right layout.
        settings=self.app.store.settings; buttons=[]
        if settings.get("quick_settings_button",True):
            b=icon_button("emblem-system-symbolic","⚙","Settings"); b.add_css_class("square"); b.connect("clicked",lambda *_:self.app.open_settings()); buttons.append(b)
        power=icon_button("system-shutdown-symbolic","⏻","Sleep, reboot or shut down"); power.add_css_class("square"); power.connect("clicked",lambda *_:self.show_power_menu()); buttons.append(power)
        if settings.get("quick_close_button",True):
            close_btn=icon_button("window-close-symbolic","✕","Close"); close_btn.add_css_class("close-button"); close_btn.add_css_class("square"); close_btn.connect("clicked",lambda *_:self.app.hide_window()); buttons.append(close_btn)
        controls=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(4)); controls.add_css_class("window-controls")
        for b in buttons: controls.append(b)
        header.append(controls)
        guide_btn=Gtk.Button(); guide_btn.add_css_class("square"); guide_btn.set_child(glyph("view-grid-symbolic","⊞")); guide_btn.set_tooltip_text("Open Applications (+)"); guide_btn.connect("clicked",lambda *_:self.app.show_mode("guide")); header.append(guide_btn); self.guide_button=guide_btn
        pane.append(header); self._header_group=buttons+[guide_btn]
        body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(10)); body.set_margin_start(S(20)); body.set_margin_end(S(20)); body.set_margin_top(S(4)); body.set_vexpand(True); pane.append(body)
        self.search_entry=Gtk.SearchEntry(); self.search_entry.connect("search-changed",lambda *_:self._refresh_search_results()); self.search_entry.connect("activate",self._activate_search)
        self.search_entry.connect("changed",self._search_typed)
        # On a TV the field is three digits wide, with what to type beside it; it stretches once letters (or a fourth
        # digit) show it is a search. At a desk it is one full-width field.
        line=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(12)); line.append(self.search_entry)
        self.channel_hint=Gtk.Label(label="Type a channel number, or letters to search"); self.channel_hint.add_css_class("channel-hint")
        self.channel_hint.set_xalign(0); self.channel_hint.set_hexpand(True); self.channel_hint.set_wrap(True); line.append(self.channel_hint)
        body.append(line); self._search_narrow=None; self._shape_search()
        self.results_scroll=Gtk.ScrolledWindow(); self.results_scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC); self.results_scroll.set_max_content_height(S(280)); self.results_scroll.set_propagate_natural_height(True); self.results_scroll.set_visible(False)
        self.results_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(2)); self.results_scroll.set_child(self.results_box); body.append(self.results_scroll)
        scroll=Gtk.ScrolledWindow(); scroll.set_vexpand(True); scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC); body.append(scroll)
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4)); scroll.set_child(content); self.quick_content=content
        self._build_quick_content(content)
        footer=Gtk.Label(); footer.add_css_class("muted"); footer.add_css_class("key-hints"); footer.set_xalign(0); footer.set_wrap(True); self.footer=footer; self._show_hints()
        footer.set_margin_start(S(20)); footer.set_margin_end(S(20)); footer.set_margin_top(S(8)); footer.set_margin_bottom(S(8)); pane.append(footer)
        pane.append(self._build_status_bar())
        return pane

    def _shape_search(self):
        """TV: a narrow channel field with its hint while the text could still be a channel number (empty, or up to
        three digits); the full width otherwise. Desktop: always the full width, without the hint."""
        e=self.search_entry; q=e.get_text(); tv=self.app.store.settings.get("use")=="tv"
        narrow=tv and (q=="" or (q.isdigit() and len(q)<=CHANNEL_DIGITS))
        if getattr(self,"_search_narrow",None)==narrow: return
        self._search_narrow=narrow
        e.set_hexpand(not narrow); e.set_halign(Gtk.Align.START if narrow else Gtk.Align.FILL)
        e.set_width_chars(CHANNEL_DIGITS+1 if narrow else -1); e.set_max_width_chars(CHANNEL_DIGITS+1 if narrow else -1)   # + the ✕ that clears it
        (e.add_css_class if narrow else e.remove_css_class)("channel-entry")
        e.set_placeholder_text("000" if narrow else "Search, or type a channel number")
        self.channel_hint.set_visible(narrow)

    def _show_hints(self):
        """The keys that work right now, named as on a remote (OK, Back) or a keyboard (Enter, Esc)."""
        footer=getattr(self,"footer",None)
        if footer is None: return
        tv=self.app.store.settings.get("use")=="tv"; ok,back=("OK","Back") if tv else ("Enter","Esc")
        if self._modal_groups: text=f"{ok}  Select    {back}  Cancel"
        elif tv: text=f"{ok}  Select    {back}  Close    {ok} on the search field  Keyboard"
        else: text=f"↑ ↓ ← →  Navigate    {ok}  Select    {back}  Close    Just type to search"
        if footer.get_text()!=text: footer.set_text(text)

    # ---------------------------------------------------------- the bottom: clock and status icons
    STATUS_PAGES=(("updates","updates"),("network","network"),("volume","sound"),("bluetooth","bluetooth"))
    def _build_status_bar(self):
        """The time and date, then icons for waiting updates, the network, the volume and Bluetooth. Each opens its
        page of the Settings app. The icons are refreshed by main.StatusWatcher."""
        bar=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(4)); bar.add_css_class("quick-status")
        clock=Gtk.Button(); clock.add_css_class("clock-button"); clock.set_hexpand(True); clock.set_tooltip_text("Date and time")
        text=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0); text.set_halign(Gtk.Align.START)
        self.clock_time=Gtk.Label(); self.clock_time.add_css_class("clock-time"); self.clock_time.set_xalign(0); text.append(self.clock_time)
        self.clock_date=Gtk.Label(); self.clock_date.add_css_class("clock-date"); self.clock_date.set_xalign(0); text.append(self.clock_date)
        clock.set_child(text); clock.connect("clicked",lambda *_:self.app.open_settings("datetime")); bar.append(clock)
        self._status_buttons={}
        for key,page in self.STATUS_PAGES:
            b=Gtk.Button(); b.add_css_class("square"); b.add_css_class("status-icon"); b.set_valign(Gtk.Align.CENTER)
            b.connect("clicked",lambda _b,p=page:self.app.open_settings(p)); bar.append(b); self._status_buttons[key]=b
        self._status_group=NavGroup([clock,*self._status_buttons.values()])
        self._status_shown=None; self.tick_clock(); self.show_status(self.app.status)
        return bar
    def tick_clock(self):
        if getattr(self,"clock_time",None) is None: return
        t=clock_text(None,self.app.store.settings.get("clock_24h",False)); d=date_text()
        if self.clock_time.get_text()!=t: self.clock_time.set_text(t)
        if self.clock_date.get_text()!=d: self.clock_date.set_text(d)
    def show_status(self,status):
        buttons=getattr(self,"_status_buttons",None)
        if not buttons or status==self._status_shown: return
        self._status_shown=status
        looks={"network":quick_status.network_icon(status),"volume":quick_status.volume_icon(status),
               "bluetooth":quick_status.bluetooth_icon(status),"updates":quick_status.updates_icon(status)}
        shown={"network":True,"volume":status.volume is not None,"bluetooth":bool(status.bluetooth),"updates":status.updates>0}
        for key,b in buttons.items():
            icon,fallback,tip=looks[key]
            if key=="updates":
                child=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(4)); child.set_halign(Gtk.Align.CENTER)
                child.append(glyph(icon,fallback,22)); n=Gtk.Label(label=str(status.updates)); n.add_css_class("status-count"); child.append(n)
                b.add_css_class("status-wide")
            else: child=glyph(icon,fallback,22)
            if key=="bluetooth": (b.add_css_class if status.bluetooth=="off" else b.remove_css_class)("status-off")
            b.set_child(child); b.set_tooltip_text(tip); b.set_visible(shown[key])

    def _build_quick_content(self,content):
        content.append(section_title("OPEN APPLICATIONS"))
        entries=self.app.workspace_entries(); outputs=self.app.wm.outputs()
        if not entries:
            content.append(muted_label("Nothing is open. Pick a favorite below, or open Applications to start something." if self.app.wm.available
                                       else "TVWCS can't see open apps here: it needs the i3 or sway window manager."))
        for entry in entries:
            content.append(self._window_row(entry.windows[0]) if len(entry.windows)==1 else self._workspace_row(entry,outputs))
        content.append(section_title("FAVORITES"))
        favorites=self.app.store.favorites()
        if not favorites: content.append(muted_label("No favorites yet. Open Applications (⊞) and press ☆ beside an app to add it here."))
        for profile in favorites: content.append(self._favorite_row(profile))

    # ---------------------------------------------------------- Quick Menu rows
    # Each row is the application (or workspace) with one ⋯ button before it. ⋯, ← on the row or a right-click opens
    # the row's menu: every option it has, each with its name (where it opens, its own shortcuts, Close, ...).
    def _favorite_row(self,p):
        app=self.app.catalogue.by_id().get(p.desktop_id)
        main=Gtk.Button(); main.add_css_class("launch-row"); main.set_hexpand(True)
        inner=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(12)); inner.append(app_icon(app.icon if app else None,p.name,32))
        if p.channel is not None:
            ch=Gtk.Label(label=f"{p.channel:03d}"); ch.add_css_class("channel-number"); inner.append(ch)
        name=Gtk.Label(label=p.name); name.set_xalign(0); name.set_hexpand(True); name.set_ellipsize(3); inner.append(name)
        if p.pin_hash: inner.append(self._lock_mark())
        main.set_child(inner)
        main.connect("clicked",lambda _b,profile=p:self.app.launch_profile(profile))
        row,group=self._options_row(main,p.name,lambda profile=p,a=app:self._profile_items(profile,a))
        self._groups["quick"].append(group); return row

    def _window_row(self,w,nested=False):
        """An application on a workspace of its own (or one app inside an expanded workspace)."""
        title,badge=extract_badge(w["title"],w.get("urgent",False))
        app=self.app.match_application_window(w)
        main=Gtk.Button(); main.add_css_class("launch-row"); main.set_hexpand(True)
        inner=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(12)); inner.append(self.app.window_icon(w,32,badge))
        label=Gtk.Label(label=title); label.set_xalign(0); label.set_hexpand(True); label.set_ellipsize(3); inner.append(label); main.set_child(inner)
        main.connect("clicked",lambda _b,con=w["con_id"]:self.app.focus_window(con))
        row,group=self._options_row(main,(app.name if app else None) or title,lambda win=w,a=app:self._window_items(win,a))
        if nested: row.set_margin_start(S(28))
        self._groups["quick"].append(group); return row

    def _workspace_row(self,entry,outputs):
        """Apps that share a workspace, grouped under a name built from what is in it."""
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(2))
        main=Gtk.Button(); main.add_css_class("launch-row"); main.set_hexpand(True); main.set_tooltip_text("Open this workspace and everything on it")
        inner=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(12)); icons=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(2))
        for w in entry.windows[:3]: icons.append(self.app.window_icon(w,24,extract_badge(w["title"],w.get("urgent",False))[1]))
        inner.append(icons)
        label=Gtk.Label(label=entry.label); label.set_xalign(0); label.set_hexpand(True); label.set_ellipsize(3); inner.append(label)
        count=Gtk.Label(label=f"{len(entry.windows)} apps"); count.add_css_class("muted"); inner.append(count); main.set_child(inner)
        main.connect("clicked",lambda _b,name=entry.name:self.app.open_workspace(name))
        others=[o["name"] for o in outputs if o["name"]!=entry.output]
        children=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(2)); children.set_visible(False)
        def items():
            shown=children.get_visible(); out=[]
            for name in others:   # only offered when there is somewhere else to send it
                out.append(("video-display-symbolic","▭",f"Move to monitor {name}",lambda n=name:self.app.move_workspace(entry.name,n),False))
            out.append(("pan-up-symbolic" if shown else "pan-down-symbolic","▴" if shown else "▾",
                        "Hide the individual apps" if shown else "Show the individual apps, to open just one",lambda:children.set_visible(not shown),False))
            out.append(("window-close-symbolic","✕","Close this workspace and its apps",
                        lambda:self.confirm("Close workspace?",f"Close {entry.label} and its {len(entry.windows)} applications? Unsaved work in them may be lost.",
                                            "Close workspace",lambda:self.app.close_workspace(entry)),True))
            return out
        row,group=self._options_row(main,entry.label,items)
        self._groups["quick"].append(group)          # registered before its children so navigation order is top to bottom
        for w in entry.windows: children.append(self._window_row(w,nested=True))
        box.append(row); box.append(children); return box

    def _options_row(self,main,title,items):
        """A row: ⋯ then the application. ⋯, ← on the application or a right-click opens the row's menu, made by
        items() when it opens: (icon, fallback glyph, label, action, dangerous). The ⋯ button can be hidden in Settings."""
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(4))
        hide=self.app.store.settings.get("hide_options_buttons",False)
        toggle=Gtk.Button(); toggle.add_css_class("options-toggle"); toggle.add_css_class("square"); toggle.set_visible(not hide)
        toggle.set_child(glyph("view-more-symbolic","⋯")); toggle.set_tooltip_text("Options")
        group=NavGroup([toggle,main],entry=main); group.toggle=toggle if not hide else None
        def open_options(*_):
            self.show_row_menu(title,items()); return True
        toggle.connect("clicked",open_options)
        click=Gtk.GestureClick(); click.set_button(3); click.connect("pressed",lambda *_a:open_options()); main.add_controller(click)
        row.append(toggle); row.append(main)
        group.expanded=lambda:False; group.expand=open_options; group.collapse=lambda:None
        group.open_options=open_options; group.menu=[toggle]
        return row,group

    def show_row_menu(self,title,items):
        """A row's menu, drawn in the window like the other dialogs: one labelled button per option, then Cancel."""
        self._begin_modal(); self._title(title); groups=[]
        if not items: self.modal_card.append(muted_label("Nothing to choose here."))
        for icon,fallback,label,action,danger in items:
            b=self.dialog_button(icon,fallback,label); b.add_css_class("menu-item")
            if danger: b.add_css_class("danger")
            b.connect("clicked",lambda _b,a=action:(self.close_modal(),a())); self.modal_card.append(b); groups.append(NavGroup([b]))
        cancel=Gtk.Button(label="Cancel"); cancel.set_margin_top(S(8)); cancel.connect("clicked",lambda *_:self.close_modal()); self.modal_card.append(cancel); groups.append(NavGroup([cancel]))
        self._modal_groups=groups; self._modal_back=self.close_modal; groups[0][0].grab_focus()

    @staticmethod
    def _lock_mark():
        mark=glyph("changes-prevent-symbolic","🔒",16); mark.set_tooltip_text("Protected by a PIN"); return mark

    def _action_items(self,app):
        """The application's own shortcuts (its .desktop actions), such as a browser's New private window."""
        if not app: return []
        return [("view-list-bullet-symbolic","≡",name,lambda a=app,aid=action_id:self.app.launch_action(a,aid),False) for action_id,name in app.desktop_actions]
    def _profile_items(self,p,app):
        """A favorite's (or search result's) menu: where it opens (kept), its shortcuts, and Close when it is open."""
        new=p.launch_mode==LAUNCH_NEW_WORKSPACE
        items=[("view-dual-symbolic","◫","Open it tiled from now on",lambda:self._toggle_mode(p.id),False) if new else
               ("view-fullscreen-symbolic","▣","Open it full screen from now on",lambda:self._toggle_mode(p.id),False)]
        items+=self._action_items(app)
        if not p.command.strip() and not p.desktop_action:
            w=self.app.wm.find_matching(p,app)
            if w is not None: items.append(("window-close-symbolic","✕",f"Close {p.name}",lambda con=w["con_id"]:self._close_open_window(con),True))
        return items
    def _window_items(self,w,app):
        """An open application's menu: open it the other way this time, its shortcuts, Close."""
        alt=LAUNCH_SAME if self.app.window_mode(w)==LAUNCH_NEW_WORKSPACE else LAUNCH_NEW_WORKSPACE
        items=[("view-dual-symbolic","◫","Show it tiled here, next to the other apps",lambda:self.app.focus_window(w["con_id"],alt),False) if alt==LAUNCH_SAME else
               ("view-fullscreen-symbolic","▣","Show it full screen, in a workspace of its own",lambda:self.app.focus_window(w["con_id"],alt),False)]
        items+=self._action_items(app)
        items.append(("window-close-symbolic","✕","Close this application",lambda:self._close_open_window(w["con_id"]),True))
        return items
    def _toggle_mode(self,profile_id):
        mode=self.app.store.toggle_launch_mode(profile_id)
        if mode: self.show_message("Opens in a workspace of its own, full screen." if mode==LAUNCH_NEW_WORKSPACE else "Opens tiled, beside the other apps.","Saved")

    def _popup(self,anchor,child):
        pop=Gtk.Popover(); pop.set_parent(anchor); pop.set_child(child); self._popovers+=1
        def closed(p): self._popovers=max(0,self._popovers-1); GLib.idle_add(p.unparent)
        pop.connect("closed",closed)
        key=Gtk.EventControllerKey(); key.connect("key-pressed",lambda _c,kv,_kc,_st:(pop.popdown(),True)[1] if kv==Gdk.KEY_Back else False); pop.add_controller(key)
        pop.popup(); return pop
    def _close_open_window(self,con_id):
        if not self.app.wm.close_window(con_id): self.app.notify_message("Could not close that application window.")
        # its row is gone once the list is rebuilt: the selection goes back to the search field, not to the header
        GLib.timeout_add(250,lambda:(self.app.refresh_data(rebuild=True),self.focus_pane_soon("search"),GLib.SOURCE_REMOVE)[2])

    # ---------------------------------------------------------- Applications pane
    def _build_guide_pane(self):
        """The Applications pane: a title over the applications guide. Its focusable widgets register into pane "guide"."""
        margin=self.app.layout.margin
        pane=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0); pane.add_css_class("pane"); pane.set_hexpand(True); pane.set_margin_start(margin)
        head=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(14)); head.set_margin_top(S(12)); head.set_margin_start(S(24)); head.set_margin_end(S(24)); head.set_margin_bottom(S(2))
        self.apps_title=Gtk.Label(label="Applications"); self.apps_title.add_css_class("pane-title"); self.apps_title.set_xalign(0); head.append(self.apps_title)
        self.apps_subtitle=Gtk.Label(); self.apps_subtitle.add_css_class("muted"); self.apps_subtitle.set_valign(Gtk.Align.END); self.apps_subtitle.set_margin_bottom(S(4)); self.apps_subtitle.set_xalign(0); head.append(self.apps_subtitle)
        pane.append(head)
        self.apps_list_scroll=Gtk.ScrolledWindow(); self.apps_list_scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC); self.apps_list_scroll.set_vexpand(True)
        self.apps_content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4)); self.apps_content.set_margin_start(S(24)); self.apps_content.set_margin_end(S(24)); self.apps_content.set_margin_bottom(S(16))
        self.apps_list_scroll.set_child(self.apps_content); pane.append(self.apps_list_scroll)
        self._rebuild_apps_content()
        return pane

    def _rebuild_apps_content(self):
        """Applications: your channels, then every installed application by category."""
        clear_box(self.apps_content)
        assigned=self.app.store.assigned()
        if self.apps_subtitle is not None: self.apps_subtitle.set_text(f"{len(assigned)} channel{'s' if len(assigned)!=1 else ''}" if assigned else "")
        self.guide_scroll=self.apps_list_scroll
        self.apps_content.append(section_title("CHANNELS"))
        if not assigned: self.apps_content.append(muted_label("No channels yet. Give an app a number with ✎, then type that number in the Quick Menu to open it."))
        for profile in assigned: self.apps_content.append(self._profile_row(profile,lineup=True))
        self.apps_content.append(section_title("ALL APPLICATIONS"))
        grouped=self.app.catalogue.by_category()
        if not grouped: self.apps_content.append(muted_label("No graphical applications were found in the XDG application directories."))
        for category,apps in grouped.items(): self.apps_content.append(self._category_section(category,apps))
        if self._guide_scroll>0:
            for delay in (30,200): GLib.timeout_add(delay,self._restore_guide_scroll)

    def _category_section(self,category,apps):
        """A focusable header button that folds its applications; open/closed state survives rebuilds."""
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(2))
        head=Gtk.Button(); head.add_css_class("category-header")
        line=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(12)); arrow=Gtk.Label(); arrow.set_width_chars(2)
        label=Gtk.Label(label=f"{category}  ({len(apps)})"); label.set_xalign(0); label.set_hexpand(True); line.append(arrow); line.append(label); head.set_child(line)
        inner=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(2)); inner.set_margin_top(S(2)); inner.set_margin_bottom(S(8))
        def apply():
            opened=category in self._expanded; inner.set_visible(opened); arrow.set_text("▾" if opened else "▸")
        def flip(*_):
            self._expanded.symmetric_difference_update({category}); apply()
        head.connect("clicked",flip); apply(); self._register("guide",head)
        for application in apps:
            default=self.app.default_profile(application)
            if default: inner.append(self._profile_row(default))
            for profile in self.app.store.for_app(application.desktop_id):
                if default and profile.id==default.id: continue
                inner.append(self._profile_row(profile))
        box.append(head); box.append(inner); return box

    def _profile_row(self,p,lineup=False):
        app=self.app.catalogue.by_id().get(p.desktop_id)
        default=self.app.default_profile(app) if app else None
        primary=default is not None and default.id==p.id
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(4)); row.add_css_class("profile-row")
        if not primary and not lineup: row.set_margin_start(S(16))   # a secondary profile hangs under its application
        main=Gtk.Button(); main.set_hexpand(True); main.add_css_class("launch-row")
        inner=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(12))
        inner.append(app_icon(app.icon if app else None,p.name,32) if (primary or lineup) else child_marker(32))
        ch=Gtk.Label(label=f"{p.channel:03d}" if p.channel is not None else ""); ch.set_width_chars(4); ch.set_xalign(0); ch.add_css_class("channel-number"); inner.append(ch)
        name=Gtk.Label(label=p.name); name.set_xalign(0); name.set_ellipsize(3); inner.append(name)
        # A main profile shows its application's description, a secondary one its launch options; either can be overridden in the editors.
        description=row_description(p,app,primary,self.app.store.app_descriptions.get(p.desktop_id,""))
        if description:
            name.set_max_width_chars(32)
            if p.pin_hash: inner.append(self._lock_mark())
            # cut with … when it does not fit: it scrolls by while the row is selected, and the pointer shows all of it
            d=Marquee(description,"description"); inner.append(d); self._descriptions.append((main,d))
            focus=Gtk.EventControllerFocus(); focus.connect("enter",lambda *_a,m=d:m.run(True)); focus.connect("leave",lambda *_a,m=d:m.run(False)); main.add_controller(focus)
            main.set_has_tooltip(True); main.connect("query-tooltip",self._description_tip,d)
        else:
            name.set_hexpand(True)
            if p.pin_hash: inner.append(self._lock_mark())
        main.set_child(inner); main.connect("clicked",lambda _b,profile=p:self.app.launch_profile(profile)); row.append(main)
        fav=Gtk.Button(); fav.add_css_class("square"); self._style_star(fav,p.favorite); self._stars.setdefault(p.id,[]).append(fav)
        fav.connect("clicked",lambda _b,profile=p:self.app.toggle_favorite(profile)); row.append(fav)
        edit=Gtk.Button(); edit.add_css_class("square"); edit.set_child(glyph("document-edit-symbolic","✎"))
        edit.set_tooltip_text("Manage application profiles" if primary else "Edit launch profile")
        if primary: edit.connect("clicked",lambda _b,profile=p:self.app.edit_application_profiles(profile.desktop_id))
        else: edit.connect("clicked",lambda _b,profile=p:self.app.edit_profile(profile,None))
        row.append(edit); self._register("guide",main,fav,edit)
        # Right-clicking the application (or ← while it is selected) opens its options too — Edit and ☆/★ —
        # which also works when the ⋯ buttons are hidden in Settings.
        pop_holder=[]
        def open_options(*_):
            box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4))
            star=Gtk.Button(label="Remove favorite" if p.favorite else "Add to favorites")
            star.connect("clicked",lambda _b:(pop_holder and pop_holder[0].popdown(),self.app.toggle_favorite(p)))
            box.append(star)
            manage=Gtk.Button(label="Manage profiles" if primary else "Edit launch profile")
            manage.connect("clicked",lambda _b:(pop_holder and pop_holder[0].popdown(),
                        self.app.edit_application_profiles(p.desktop_id) if primary else self.app.edit_profile(p,None)))
            box.append(manage)
            pop_holder.append(self._popup(main,box)); return True
        click=Gtk.GestureClick(); click.set_button(3); click.connect("pressed",lambda *_a:open_options()); main.add_controller(click)
        group=self._groups["guide"][-1]
        if group:
            group.entry=main; group.open_options=open_options
            group.expand=lambda:open_options(); group.expanded=lambda:bool(pop_holder and pop_holder[-1].get_visible())
        return row

    @staticmethod
    def _description_tip(_widget,_x,_y,_keyboard,tooltip,marquee):
        if not marquee.truncated: return False
        tooltip.set_text(marquee.text); return True
    def apps_width(self):
        """At a desk the Applications pane is only as wide as its rows need: the widest row without its description,
        plus room for most descriptions (four in five) in full. The rest are cut with … (see Marquee)."""
        if self.guide_pane is None:
            self.guide_pane=self._build_guide_pane(); self.panes.append(self.guide_pane); self.guide_pane.set_visible(self.guide_open)
        rows=[]; texts=[]
        for main,d in self._descriptions:
            row=main.get_parent()
            if row is None: continue
            rows.append(row.measure(Gtk.Orientation.HORIZONTAL,-1)[1]-d.label.measure(Gtk.Orientation.HORIZONTAL,-1)[1])
            texts.append(d.label.measure(Gtk.Orientation.HORIZONTAL,-1)[1])
        if not rows: return S(640)
        texts.sort(); most=texts[min(len(texts)-1,int(len(texts)*0.8))]
        return max(rows)+most+2*S(24)+S(16)   # the list's side margins, and its scroll bar
    def _style_star(self,button,favorite):
        button.set_child(glyph("starred-symbolic" if favorite else "non-starred-symbolic","★" if favorite else "☆"))
        button.set_tooltip_text("Remove favorite" if favorite else "Add to favorites")
    def refresh_favorites(self,profile_id):
        """A favorite changed: restyle its star(s) and rebuild only the Quick Menu list; Applications stays put."""
        p=self.app.store.get(profile_id)
        for b in self._stars.get(profile_id,[]): self._style_star(b,bool(p and p.favorite))
        if self.quick_content is not None:
            self._groups["quick"]=[]; clear_box(self.quick_content); self._build_quick_content(self.quick_content)
    def _restore_guide_scroll(self):
        if self.guide_scroll is not None: self.guide_scroll.get_vadjustment().set_value(self._guide_scroll)
        return GLib.SOURCE_REMOVE
    def reset_scroll(self): self._guide_scroll=0.0

    # ---------------------------------------------------------- search
    def _refresh_search_results(self):
        if not hasattr(self,"results_box"): return
        clear_box(self.results_box); self._result_groups=[]; self._result_mains=[]; self._selected_result=0
        q=self.search_entry.get_text()
        self.results_scroll.set_visible(bool(q.strip()))
        self._shape_search()
        if not q.strip(): self._search_results=[]; return
        self._search_results=search_items(q,self.app.store.profiles,self.app.catalogue.by_id(),self.app.wm.windows())[:12]
        if not self._search_results:
            self.results_box.append(muted_label("No matches. Try an app name, profile name, channel number, or window title.")); return
        for i,result in enumerate(self._search_results):
            main=Gtk.Button(); main.add_css_class("launch-row"); main.set_hexpand(True)
            row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(10))
            if result["kind"]=="window":
                w=result["window"]; row.append(self.app.window_icon(w,28,result.get("badge"))); app=self.app.match_application_window(w)
                items=lambda w=w,a=app:self._window_items(w,a)
            else:
                p=result["profile"]; app=self.app.catalogue.by_id().get(p.desktop_id); row.append(app_icon(app.icon if app else None,p.name,28))
                items=lambda p=p,a=app:self._profile_items(p,a)
            label=Gtk.Label(label=result["label"]); label.set_xalign(0); label.set_hexpand(True); label.set_ellipsize(3); row.append(label)
            detail=Gtk.Label(label=result["detail"]); detail.add_css_class("muted"); detail.set_ellipsize(3); row.append(detail); main.set_child(row)
            if i==self._selected_result: main.add_css_class("tvwcs-selected")
            main.connect("clicked",lambda _b,r=result:self.app.activate_result(r))
            line,group=self._options_row(main,result["label"].strip(),items); self._result_groups.append(group); self._result_mains.append(main); self.results_box.append(line)
    def _activate_search(self,*_):
        if self._channel_source: GLib.source_remove(self._channel_source); self._channel_source=0   # Enter launches it now
        q=self.search_entry.get_text().strip()
        if q.isdigit():
            p=next((p for p in self.app.store.profiles if p.channel==int(q)),None)
            if p: self.app.launch_profile(p); return
        if self._search_results: self.app.activate_result(self._search_results[self._selected_result])
    def _search_typed(self,*_):
        """A full channel number (three digits) left alone for a second launches its channel, without Enter."""
        if self._channel_source: GLib.source_remove(self._channel_source); self._channel_source=0
        q=self.search_entry.get_text().strip()
        if len(q)==CHANNEL_DIGITS and q.isdigit() and any(p.channel==int(q) for p in self.app.store.profiles):
            self._channel_source=GLib.timeout_add(CHANNEL_DELAY,self._launch_typed_channel,q)
    def _launch_typed_channel(self,q):
        self._channel_source=0
        if self.is_visible() and not self._modal_groups and self.search_entry.get_text().strip()==q:
            p=next((p for p in self.app.store.profiles if p.channel==int(q)),None)
            if p: self.app.launch_profile(p)
        return GLib.SOURCE_REMOVE
    def _select_result(self,index):
        self._selected_result=index
        for i,b in enumerate(self._result_mains):
            b.remove_css_class("tvwcs-selected")
            if i==index: b.add_css_class("tvwcs-selected")
        # the highlight moves while the selection stays in the search field, so the list does not follow it by itself
        if 0<=index<len(self._result_mains): scroll_to_show(self.results_scroll,self._result_mains[index])
    def _type_to_search(self,text):
        e=self.search_entry; value=e.get_text()+text
        e.grab_focus(); e.set_text(value); e.set_position(-1)

    # ---------------------------------------------------------- remote / keyboard navigation
    def _register(self,pane,*widgets,entry=None):
        group=NavGroup([w for w in widgets if w is not None],entry)
        if group: self._groups[pane].append(group); return group
        return None
    def _focus_changed(self,*_):
        w=self.get_focus()
        if w is not None: self._last_focus[self._pane_of(w)]=w
        self._fold_options(w)
        self._schedule_focus_tip(w)
    def _fold_options(self,focused):
        """Close a Quick Menu row's options once the selection has left them. Not while a pop-up menu (desktop
        actions, monitors) or a dialog opened from one of them is up: those come back to the option afterwards."""
        row=self._open_row
        if row is None or focused is None or self._popovers or self._modal_groups: return
        if any(focused is w for w in row.menu): return
        self._open_row=None
        if row.expanded(): row.collapse()

    # ---------------------------------------------------------- tooltips for selected icon-only buttons
    # A remote has no pointer to hover with, so a button with no text shows its tooltip once it has been selected for a moment.
    def _schedule_focus_tip(self,w):
        self._hide_focus_tip()
        if w is not None and icon_only(w) and self.app.store.settings.get("button_hints",False):
            self._focus_tip_source=GLib.timeout_add(FOCUS_TIP_DELAY,self._show_focus_tip,w)
    def _show_focus_tip(self,button):
        self._focus_tip_source=0
        hovered=self.pointer.active and button.get_state_flags() & Gtk.StateFlags.PRELIGHT   # the pointer is on it: GTK's own tooltip is showing
        if self.get_focus() is not button or not usable(button) or hovered or self._focus_tip is not None: return GLib.SOURCE_REMOVE
        tip=Gtk.Label(label=button.get_tooltip_text()); tip.set_wrap(True); tip.set_max_width_chars(48)
        pop=Gtk.Popover(); pop.add_css_class("focus-tip"); pop.set_autohide(False); pop.set_can_focus(False); pop.set_has_arrow(False)
        pop.set_position(Gtk.PositionType.BOTTOM); pop.set_child(tip); pop.set_parent(button); pop.popup()
        self._focus_tip=pop; self._focus_tip_source=GLib.timeout_add(FOCUS_TIP_DURATION,self._expire_focus_tip)
        return GLib.SOURCE_REMOVE
    def _expire_focus_tip(self):
        self._focus_tip_source=0; self._hide_focus_tip(); return GLib.SOURCE_REMOVE
    def _hide_focus_tip(self):
        if self._focus_tip_source: GLib.source_remove(self._focus_tip_source); self._focus_tip_source=0
        pop=self._focus_tip; self._focus_tip=None
        if pop is not None:
            pop.popdown()
            if pop.get_parent() is not None: pop.unparent()
    def _pane_of(self,widget):
        for name,pane in (("options",self.options_pane),("guide",self.guide_pane)):
            if widget is not None and pane is not None and (widget is pane or widget.is_ancestor(pane)): return name
        return "quick"
    def _ordered_groups(self,pane):
        if self._modal_groups: return self._modal_groups
        if pane!="quick": return list(self._groups[pane])
        return [self._header_group,[self.search_entry]]+list(self._result_groups)+list(self._groups["quick"])+[getattr(self,"_status_group",[])]
    @staticmethod
    def _contains(widget,focused): return focused is not None and (focused is widget or focused.is_ancestor(widget))
    def _in_search(self,focused): return self._contains(self.search_entry,focused)   # focus sits on the entry's inner text widget
    def _group_index(self,groups,focused):
        # An exact match wins; only then accept "inside" (an entry's inner text widget). Otherwise a button nested in
        # a container that is itself a group would be mistaken for that container.
        for i,g in enumerate(groups):
            if any(w is focused for w in g): return i
        for i,g in enumerate(groups):
            if any(self._contains(w,focused) for w in g): return i
        return -1
    def _landing(self,group,column=None):
        if column is not None and getattr(group,"column",False):   # a grid row: stay in the same column
            active=[w for w in group if usable(w)]
            if active: return active[min(column,len(active)-1)]
        entry=getattr(group,"entry",None)
        if entry is not None and usable(entry): return entry
        return next((w for w in group if usable(w)),None)
    def _focus_first(self,groups):
        for g in groups:
            w=self._landing(g)
            if w is not None and w.grab_focus(): return True
        return False
    def focus_pane(self,pane):
        """Select something in a pane: where the selection last was in it, else its first row. "search": the Quick
        Menu's search field, whatever was selected before (GTK selects the first button when the window appears)."""
        if pane=="search": return self.search_entry.grab_focus()
        last=self._last_focus.get(pane)
        if last is not None and usable(last) and last.grab_focus(): return True
        if pane=="quick": return self.search_entry.grab_focus()
        return self._focus_first(self._groups[pane])
    def focus_pane_soon(self,pane):
        """Focus once a freshly shown panel has been mapped."""
        GLib.timeout_add(70,lambda:(self.focus_pane(pane),GLib.SOURCE_REMOVE)[1])
    def _move_group(self,step):
        focused=self.get_focus(); pane=self._pane_of(focused)
        groups=[g for g in self._ordered_groups(pane) if any(usable(w) for w in g)]
        if not groups: return False
        current=self._group_index(groups,focused)
        lane=getattr(groups[current],"lane",None) if current>=0 else None
        if lane is not None:   # in a column layout ↑/↓ stays in its column (rows outside any column are shared)
            groups=[g for g in groups if getattr(g,"lane",None) in (None,lane)]; current=self._group_index(groups,focused)
        column=next((k for k,w in enumerate(groups[current]) if w is focused),None) if current>=0 else None
        start=(current+step)%len(groups) if current>=0 else (0 if step>0 else len(groups)-1)
        for offset in range(len(groups)):
            w=self._landing(groups[(start+step*offset)%len(groups)],column)
            if w is not None and w.grab_focus(): return True
        return False
    def _move_within_group(self,step):
        focused=self.get_focus(); pane=self._pane_of(focused)
        groups=self._ordered_groups(pane); gi=self._group_index(groups,focused)
        if gi<0: return False
        group=groups[gi]; active=[w for w in group if usable(w)]
        if not active: return False
        i=next((k for k,w in enumerate(active) if w is focused),None)
        if i is None: i=next((k for k,w in enumerate(active) if self._contains(w,focused)),0)
        open_options=getattr(group,"open_options",None)
        if step<0 and pane=="quick" and open_options is not None and focused is group.entry and group.expanded is not None and not group.expanded():
            return open_options()   # ← on a Quick Menu row opens its options, next to the application
        nxt=i+step
        if 0<=nxt<len(active): return active[nxt].grab_focus()
        if self._modal_groups: return active[nxt%len(active)].grab_focus()
        if getattr(group,"lane",None) is not None and self._jump_lane(groups,group,active[i],step): return True
        toggle=getattr(group,"toggle",None)
        if step<0:
            if toggle is not None and active[i] is toggle:
                if any(group is g for g in self._result_groups): self.search_entry.grab_focus()   # back to typing
                return True
            if pane=="guide": return self.focus_pane("quick")
            if pane=="options": self.app.show_panels(True,False,focus="guide"); return True
            return active[nxt%len(active)].grab_focus()
        # Past the right-hand end: continue into the next panel, opening it if it is closed.
        if pane=="quick":
            if self.guide_open: return self.focus_pane("guide")
            self.app.show_panels(True,False,focus="guide"); return True
        if pane=="guide" and self.options_open: return self.focus_pane("options")
        return True
    def _jump_lane(self,groups,group,focused,step):
        """←/→ past the edge of a row in a column layout: go to the row beside it in the neighbouring column."""
        target=group.lane+step
        candidates=[g for g in groups if getattr(g,"lane",None)==target and self._landing(g) is not None]
        if not candidates: return False
        y=self._middle_y(focused)
        best=min(candidates,key=lambda g:abs(self._middle_y(self._landing(g))-y))
        return self._landing(best).grab_focus()
    def _middle_y(self,widget):
        try:
            ok,rect=widget.compute_bounds(self)
            return rect.get_y()+rect.get_height()/2 if ok else 0.0
        except (AttributeError,TypeError,ValueError): return 0.0
    def _result_index(self,focused):
        for i,g in enumerate(self._result_groups):
            if any(w is focused for w in g): return i
        return -1

    def _key_pressed(self,_controller,keyval,_keycode,state):
        if self._capture is not None and self._capture_key(keyval,state): return True
        self._hide_focus_tip()   # any key press dismisses it; the next selection schedules a fresh one
        focused=self.get_focus(); editable=isinstance(focused,Gtk.Editable); typing=self._in_search(focused)
        if keyval in (Gdk.KEY_Escape,Gdk.KEY_Back): self._escape(); return True   # the remote's Back key (XF86Back) is Esc
        if self._pin is not None and self._pin_key(keyval): return True
        if self._chan is not None and self._chan_key(keyval): return True
        if self._text is not None and not editable and self._text_key(keyval): return True
        # Typing anywhere starts a search (not while a dialog is up, in another text field, or with a shortcut modifier held).
        if not self._modal_groups and not editable and not (state & _TYPING_BLOCKED):
            ch=Gdk.keyval_to_unicode(keyval)
            if ch>32 and chr(ch).isprintable(): self._type_to_search(chr(ch)); return True
        if keyval in (Gdk.KEY_Down,Gdk.KEY_Up):
            step=1 if keyval==Gdk.KEY_Down else -1
            if not self._modal_groups:
                # Keep focus in the search field while arrows change the highlighted result so typing can continue.
                if typing and self.search_entry.get_text().strip() and self._search_results:
                    nxt=self._selected_result+step
                    if 0<=nxt<len(self._search_results): self._select_result(nxt); return True
                    if step>0: self._focus_first(self._groups["quick"]); return True
                    if self._header_group: self._header_group[0].grab_focus()
                    return True
                ri=self._result_index(focused)
                if ri>=0:
                    nxt=ri+step
                    if 0<=nxt<len(self._result_groups): self._select_result(nxt); self._landing(self._result_groups[nxt]).grab_focus(); return True
                    if step>0: self._focus_first(self._groups["quick"]); return True
                    self.search_entry.grab_focus(); return True
            self._move_group(step); return True
        if keyval==Gdk.KEY_Right and typing and self._search_results and not self._modal_groups \
                and self.search_entry.get_position()==len(self.search_entry.get_text()):
            g=self._result_groups[self._selected_result]   # at the end of the text, Right opens the highlighted result's menu
            if g.open_options is not None: g.open_options(); return True
        if keyval in (Gdk.KEY_Left,Gdk.KEY_Right) and not editable:
            if self._move_within_group(1 if keyval==Gdk.KEY_Right else -1): return True
        if keyval in (Gdk.KEY_Return,Gdk.KEY_KP_Enter) and typing:
            if not self.search_entry.get_text().strip(): self.ask_search(); return True   # Enter on an empty search: the on-screen keyboard
            self._activate_search(); return True
        return False
    def _key_released(self,_controller,keyval,_keycode,state):
        if self._capture is not None:
            spec=self._capture.release(Gdk.keyval_name(keyval))
            if spec: self._end_capture(spec)
    def _escape(self):
        if self._modal_groups: (self._modal_back or self.close_modal)(); return
        if self.guide_open: self.app.show_panels(False,False,focus="quick"); return    # then Applications, keep the Quick Menu
        self.app.hide_window()

    # ---------------------------------------------------------- close when focus leaves
    def _active_changed(self,*_):
        if self.is_active():
            self._was_active=True
            # Clicking TVWCS brings it in front of an open dialog (profile editor, application profiles), which would
            # then sit hidden behind it, blocking it. Close the dialogs instead, dropping what was not saved.
            if self.app.has_dialogs(): GLib.timeout_add(120,self._dismiss_dialogs_if_active)
            return
        if self._was_active and self.is_visible() and self.app.store.settings["close_on_click_outside"]:
            GLib.timeout_add(150,self._close_if_unfocused)
    def _close_if_unfocused(self):
        # Child windows (profile editor) and open popovers legitimately take focus; only a click elsewhere closes TVWCS.
        if self.is_visible() and not self.is_active() and self._popovers==0 and not self.app.has_dialogs(): self.app.hide_window()
        return GLib.SOURCE_REMOVE
    def _dismiss_dialogs_if_active(self):
        if self.is_visible() and self.is_active(): self.app.dismiss_dialogs()   # still in front: not a passing focus change
        return GLib.SOURCE_REMOVE
    def note_shown(self): self._was_active=False; self._hide_focus_tip()

    # ---------------------------------------------------------- dialogs (drawn over the panels, remote-navigable)
    def _begin_modal(self):
        if not self._modal_groups: self._return_focus=self.get_focus()
        clear_box(self.modal_card); self.modal_card.set_size_request(self._card_width,-1)
        self.modal_reveal.set_visible(True); self.modal_reveal.set_can_target(True); self.modal_reveal.set_reveal_child(True)
        GLib.idle_add(lambda:(self._show_hints(),GLib.SOURCE_REMOVE)[1])
    def close_modal(self):
        if self._text is not None and self._text.get("secret"): self._text["entry"].set_text("")   # a typed password is never left in the widget
        self._modal_groups=[]; self._modal_back=None; self._capture=None; self._pin=None; self._text=None; self._chan=None
        self.modal_reveal.set_can_target(False); self.modal_reveal.set_reveal_child(False); self.modal_reveal.set_visible(False); self._show_hints()
        back=self._return_focus
        if back is not None and usable(back): back.grab_focus()
        else: self.focus_pane("quick")
    def _title(self,text):
        t=Gtk.Label(label=text); t.add_css_class("pane-title"); t.set_xalign(0); t.set_wrap(True); t.set_margin_bottom(S(8)); self.modal_card.append(t)
    def dialog_button(self,icon,fallback,text):
        b=Gtk.Button(); b.add_css_class("dialog-button"); row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(14))
        g=glyph(icon,fallback,24) if icon else Gtk.Label(); g.set_size_request(S(28),-1); row.append(g)
        l=Gtk.Label(label=text); l.set_xalign(0); l.set_hexpand(True); l.set_wrap(True); l.set_max_width_chars(34)   # long labels wrap inside the Quick Menu
        row.append(l); b.set_child(row); return b

    def show_message(self,message,title="Something went wrong",done=None):
        """A message with an OK button, drawn in the window (no separate dialog window to lose behind TVWCS)."""
        self._begin_modal(); self._title(title)
        text=muted_label(message); text.set_margin_bottom(S(14)); self.modal_card.append(text)
        finish=lambda:(self.close_modal(),done and done())
        ok=Gtk.Button(label="OK"); ok.add_css_class("active"); ok.connect("clicked",lambda *_:finish()); self.modal_card.append(ok)
        self._modal_groups=[NavGroup([ok])]; self._modal_back=finish; ok.grab_focus()
    def show_starting(self,name,on_back):
        """“Starting Kodi…” while an application opens its first window (main.App waits for it)."""
        self._begin_modal(); self._title(f"Starting {name}…")
        spinner=Gtk.Spinner(); spinner.set_size_request(S(48),S(48)); spinner.set_halign(Gtk.Align.START); spinner.set_margin_bottom(S(10)); spinner.start(); self.modal_card.append(spinner)
        text=muted_label("It opens in a moment. Some apps take a few seconds the first time."); self.modal_card.append(text); self._starting_text=text
        hide=Gtk.Button(label="Hide"); hide.set_margin_top(S(12)); hide.connect("clicked",lambda *_:on_back()); self.modal_card.append(hide)
        self._modal_groups=[NavGroup([hide])]; self._modal_back=on_back; hide.grab_focus()
    def starting_slow(self,name):
        if getattr(self,"_starting_text",None) is not None and self._modal_groups:
            self._starting_text.set_text(f"{name} has not opened a window yet. It may still be starting, or it may not have started.")
    def first_run(self,done):
        """The first time TVWCS opens: where it is used (TV or desk), then how to add favorites."""
        def picked(use):
            self.app.set_use(use)
            self.show_message("Press ⊞ to see every application. Press ☆ beside the ones you use most to add them to this menu, "
                              "and ✎ to give one a channel number or a hotkey. Everything else is in Settings (⚙).",
                              "Welcome to TVWCS",done)
        self._begin_modal(); self._title("Welcome to TVWCS")
        self.modal_card.append(muted_label("Where is this computer used? You can change this later in Settings."))
        groups=[]
        for key,label,icon,fallback in (("tv","On a TV, with a remote","video-display-symbolic","▭"),("desktop","At a desk, with a mouse and keyboard","input-mouse-symbolic","🖱")):
            b=self.dialog_button(icon,fallback,label); b.connect("clicked",lambda _b,k=key:picked(k)); self.modal_card.append(b); groups.append(NavGroup([b]))
        self._modal_groups=groups; self._modal_back=lambda:picked("tv"); groups[0][0].grab_focus()

    def confirm(self,title,message,label,on_confirm,back=None):
        """Ask before doing something destructive. Cancel is focused, so a stray Enter is harmless."""
        self._begin_modal(); self._title(title)
        text=muted_label(message); text.set_margin_bottom(S(14)); self.modal_card.append(text)
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(6)); row.set_homogeneous(True)
        cancel=Gtk.Button(label="Cancel"); cancel.connect("clicked",lambda *_:(back or self.close_modal)()); row.append(cancel)
        go=Gtk.Button(label=label); go.add_css_class("danger"); go.connect("clicked",lambda *_:(self.close_modal(),on_confirm())); row.append(go)
        self.modal_card.append(row); self._modal_groups=[[cancel,go]]; self._modal_back=back or self.close_modal; cancel.grab_focus()

    def show_power_menu(self):
        """Sleep, reboot and shut down; Log out when there is a login screen to go back to, and Lock when it is
        switched on in Options."""
        self._begin_modal(); self._title("Power"); groups=[]
        for action in power_menu(self.app.store.settings):
            b=self.dialog_button(action.icon,action.fallback,action.label); b.connect("clicked",lambda _b,a=action:(self.close_modal(),self.system_action(a)))
            self.modal_card.append(b); groups.append(NavGroup([b]))
        cancel=Gtk.Button(label="Cancel"); cancel.set_margin_top(S(8)); cancel.connect("clicked",lambda *_:self.close_modal()); self.modal_card.append(cancel); groups.append(NavGroup([cancel]))
        self._modal_groups=groups; self._modal_back=self.close_modal; groups[0][0].grab_focus()

    def system_action(self,action):
        if action.confirm: self.confirm(f"{action.label}?",action.confirm,action.label,lambda a=action:self._execute(a))
        else: self._execute(action)
    def _execute(self,action):
        if action.id=="refresh": self.app.refresh_data(rebuild=True)
        else: self.app.run_system_action(action.id)

    def ask_pin(self,profile,on_ok,message=""):
        """A PIN keypad that works with a D-pad (and with digit keys). Runs on_ok() once the right PIN is entered."""
        self._begin_modal(); self._title(f"PIN for {profile.name}")
        shown=Gtk.Label(); shown.add_css_class("pin-display"); shown.set_margin_bottom(S(8)); self.modal_card.append(shown)
        if message:
            e=Gtk.Label(label=message); e.add_css_class("error"); e.set_wrap(True); e.set_margin_bottom(S(8)); self.modal_card.append(e)
        self._pin={"profile":profile,"on_ok":on_ok,"digits":"","shown":shown}; self._pin_refresh()
        groups=[]
        def key(text,handler,css=None):
            b=Gtk.Button(label=text); b.add_css_class("pin-key")
            if css: b.add_css_class(css)
            b.connect("clicked",lambda *_:handler()); return b
        for digits in (("1","2","3"),("4","5","6"),("7","8","9"),(None,"0",None)):
            line=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(4)); line.set_homogeneous(True); line.set_margin_bottom(S(4)); row=[]
            for d in digits:
                if d is not None: b=key(d,lambda d=d:self._pin_press(d))
                elif not row: b=key("⌫",self._pin_back)
                else: b=key("OK",self._pin_submit,"active")
                line.append(b); row.append(b)
            self.modal_card.append(line); g=NavGroup(row); g.column=True; groups.append(g)
        cancel=Gtk.Button(label="Cancel"); cancel.set_margin_top(S(6)); cancel.connect("clicked",lambda *_:self.close_modal()); self.modal_card.append(cancel); groups.append(NavGroup([cancel]))
        self._modal_groups=groups; self._modal_back=self.close_modal; groups[0][0].grab_focus()
    def _pin_refresh(self):
        n=len(self._pin["digits"]); self._pin["shown"].set_text("  ".join("●"*n) if n else "– – – –")
    def _pin_press(self,digit):
        if len(self._pin["digits"])<8: self._pin["digits"]+=digit; self._pin_refresh()
    def _pin_back(self):
        self._pin["digits"]=self._pin["digits"][:-1]; self._pin_refresh()
    def _pin_key(self,keyval):
        """Digit and Backspace keys also work on the keypad (the remote's number keys, a keyboard)."""
        ch=Gdk.keyval_to_unicode(keyval)
        if 48<=ch<=57: self._pin_press(chr(ch)); return True
        if keyval==Gdk.KEY_BackSpace: self._pin_back(); return True
        return False
    def _pin_submit(self):
        st=self._pin; profile=st["profile"]
        status,wait=self.app.pin_gate.attempt(profile.id,st["digits"],profile.pin_hash)
        if status=="ok": on_ok=st["on_ok"]; self.close_modal(); on_ok(); return
        self.ask_pin(profile,st["on_ok"],"Wrong PIN." if status=="wrong" else f"Too many wrong tries. Try again in {wait} seconds.")

    def ask_channel(self,title,callback,current="",back=None):
        """A channel number in three boxes of one digit each, typed on the keypad (or the remote's number keys). The
        boxes start empty, so a new number replaces the old one without deleting it first. callback(text) gets the
        digits typed ("7" is channel 007), the current number when OK is pressed with nothing typed, or "" for No channel."""
        self._begin_modal(); self._title(title)
        m=muted_label("000 to 999. Type it in the Quick Menu to open this app."+(f" Now: {int(current):03d}." if str(current).strip().isdigit() else ""))
        m.set_margin_bottom(S(8)); self.modal_card.append(m)
        boxes=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(8)); boxes.set_halign(Gtk.Align.CENTER); boxes.set_margin_bottom(S(10)); cells=[]
        for _ in range(3):
            c=Gtk.Label(); c.add_css_class("digit-box"); boxes.append(c); cells.append(c)
        self.modal_card.append(boxes)
        cancelled=back or self.close_modal
        def submit():
            typed=self._chan["digits"]; self.close_modal(); callback(typed if typed else str(current or ""))
        def none(): self.close_modal(); callback("")
        self._chan={"digits":"","cells":cells}; self._chan_refresh()
        groups=[]
        def key(text,handler,css=None):
            b=Gtk.Button(label=text); b.add_css_class("pin-key")
            if css: b.add_css_class(css)
            b.connect("clicked",lambda *_:handler()); return b
        for row in (("1","2","3"),("4","5","6"),("7","8","9"),("⌫","0","OK")):
            line=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(4)); line.set_homogeneous(True); line.set_margin_bottom(S(4)); made=[]
            for d in row:
                b=key(d,self._chan_back) if d=="⌫" else key("OK",submit,"active") if d=="OK" else key(d,lambda d=d:self._chan_press(d))
                line.append(b); made.append(b)
                if d=="OK": self._chan["ok"]=b
            self.modal_card.append(line); g=NavGroup(made); g.column=True; groups.append(g)
        bottom=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(6)); bottom.set_homogeneous(True); bottom.set_margin_top(S(6))
        clear=Gtk.Button(label="No channel"); clear.connect("clicked",lambda *_:none()); bottom.append(clear)
        cancel=Gtk.Button(label="Cancel"); cancel.connect("clicked",lambda *_:cancelled()); bottom.append(cancel)
        self.modal_card.append(bottom); groups.append(NavGroup([clear,cancel]))
        self._modal_groups=groups; self._modal_back=cancelled; groups[0][0].grab_focus()
    def _chan_refresh(self):
        digits=self._chan["digits"]
        for i,c in enumerate(self._chan["cells"]):
            c.set_text(digits[i] if i<len(digits) else "–")
            (c.add_css_class if i==len(digits) else c.remove_css_class)("current")
    def _chan_press(self,digit):
        if len(self._chan["digits"])<3: self._chan["digits"]+=digit; self._chan_refresh()
        if len(self._chan["digits"])==3 and self._chan.get("ok") is not None: self._chan["ok"].grab_focus()   # complete: OK is next
    def _chan_back(self):
        self._chan["digits"]=self._chan["digits"][:-1]; self._chan_refresh()
    def _chan_key(self,keyval):
        ch=Gdk.keyval_to_unicode(keyval)
        if 48<=ch<=57: self._chan_press(chr(ch)); return True
        if keyval==Gdk.KEY_BackSpace: self._chan_back(); return True
        return False

    def ask_password(self,action_label,on_ok,message=""):
        """The administrator (sudo) password for a power action, typed on a keyboard (such as the one on the back of a
        remote) or on the on-screen keyboard: the full one, or the number pad when Settings > Options > Password
        keyboard says so. Either can switch to the other. on_ok(password) runs on OK; the field is emptied when it closes."""
        def got(password):
            if password: on_ok(password)
        self.ask_text(f"Password for {action_label}",got,"",f"{action_label} needs administrator rights. Enter your password (the one sudo asks for). "
                      "It is used once and never stored.",digits=self.app.store.settings.get("password_keyboard")=="digits",secret=True,switchable=True,error=message)

    # ---------------------------------------------------------- the on-screen keyboard (typing with a remote)
    KEYS={"lower":("1234567890","qwertyuiop","asdfghjkl'","zxcvbnm,.-"),
          "upper":("1234567890","QWERTYUIOP","ASDFGHJKL\"","ZXCVBNM;:_"),
          "symbols":("!@#$%^&*()","~`+=[]{}\\|","/?<>€£¥§°¿","…·•×÷¡«»¢¤")}
    def ask_text(self,title,callback,initial="",message="",back=None,digits=False,secret=False,ok_label="OK",max_len=0,switchable=False,error=""):
        """Type a piece of text with the D-pad: a full keyboard (letters, capitals, symbols) or, with digits, a number
        keypad. A real keyboard types into it too. callback(text) runs on OK or Enter; Cancel or Back runs back()
        (or just closes). With switchable (passwords), a key changes between the two keyboards, keeping what is typed."""
        self._begin_modal(); self._title(title)
        if message:
            m=muted_label(message); m.set_margin_bottom(S(8)); self.modal_card.append(m)
        if error:
            e=Gtk.Label(label=error); e.add_css_class("error"); e.set_wrap(True); e.set_xalign(0); e.set_margin_bottom(S(8)); self.modal_card.append(e)
        entry=Gtk.PasswordEntry() if secret else Gtk.Entry()
        if secret: entry.set_show_peek_icon(True)
        entry.add_css_class("pin-display" if digits else "text-display"); entry.set_text(initial or ""); entry.set_margin_bottom(S(8))
        if max_len and not secret: entry.set_max_length(max_len)
        self.modal_card.append(entry)
        cancelled=back or self.close_modal
        def submit(*_):
            text=entry.get_text(); self.close_modal(); callback(text)
        entry.connect("activate",submit)
        self._text={"entry":entry,"submit":submit,"layer":"lower","keys":[],"digits":digits,"max":max_len,"secret":secret}
        def switch():   # the other keyboard, with what is typed so far
            typed=entry.get_text()
            self.ask_text(title,callback,typed,message,back,not digits,secret,ok_label,max_len,switchable,error)
        groups=[NavGroup([entry])]
        def key(text,handler,css=None):
            b=Gtk.Button(label=text); b.add_css_class("pin-key")
            if css: b.add_css_class(css)
            b.connect("clicked",lambda *_:handler()); return b
        def line(buttons):
            box=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(4)); box.set_homogeneous(True); box.set_margin_bottom(S(4))
            for b in buttons: box.append(b)
            self.modal_card.append(box); g=NavGroup(buttons); g.column=True; groups.append(g)
        if digits:
            for row in (("1","2","3"),("4","5","6"),("7","8","9")): line([key(d,lambda d=d:self._type(d)) for d in row])
            line([key("⌫",self._erase),key("0",lambda:self._type("0")),key(ok_label,submit,"active")])
            if switchable: line([key("ABC  Full keyboard",switch)])
        else:
            for r in range(4):
                buttons=[key("",lambda r=r,c=c:self._type(self.KEYS[self._text["layer"]][r][c]),"kb-key") for c in range(10)]
                self._text["keys"].append(buttons); line(buttons)
            if switchable:   # passwords: the number pad, for a password of digits only
                pad=key("123  Number pad",switch); pad.add_css_class("kb-key"); self.modal_card.append(pad); groups.append(NavGroup([pad]))
            shift=key("⇧",lambda:self._layer("lower" if self._text["layer"]=="upper" else "upper"))
            symbols=key("&123",lambda:self._layer("lower" if self._text["layer"]=="symbols" else "symbols"))
            space=key("Space",lambda:self._type(" ")); erase=key("⌫",self._erase); ok=key(ok_label,submit,"active")
            box=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(4)); box.set_margin_bottom(S(4))
            for b in (shift,symbols,space,erase,ok): b.add_css_class("kb-key"); box.append(b)
            space.set_hexpand(True)
            for b,w in ((shift,56),(symbols,64),(erase,56),(ok,88)): b.set_size_request(S(w),-1)
            self.modal_card.append(box); g=NavGroup([shift,symbols,space,erase,ok]); groups.append(g)
            self._text["shift"]=shift; self._text["symbols"]=symbols; self._label_keys()
        cancel=Gtk.Button(label="Cancel"); cancel.set_margin_top(S(6)); cancel.connect("clicked",lambda *_:cancelled()); self.modal_card.append(cancel); groups.append(NavGroup([cancel]))
        self._modal_groups=groups; self._modal_back=cancelled
        first=groups[1][0]; first.grab_focus()
        GLib.timeout_add(150,lambda:(self._text is not None and self._text["entry"] is entry and self.get_focus() is None and first.grab_focus(),GLib.SOURCE_REMOVE)[1])
    def _label_keys(self):
        st=self._text; rows=self.KEYS[st["layer"]]
        for r,buttons in enumerate(st["keys"]):
            for c,b in enumerate(buttons): b.set_label(rows[r][c])
        (st["shift"].add_css_class if st["layer"]=="upper" else st["shift"].remove_css_class)("active")
        st["symbols"].set_label("abc" if st["layer"]=="symbols" else "&123")
    def _layer(self,name):
        self._text["layer"]=name; self._label_keys()
    def _type(self,text):
        st=self._text; e=st["entry"]; value=e.get_text()
        if st["max"] and len(value)>=st["max"]: return
        e.set_text(value+text)
        if st["layer"]=="upper" and not st["digits"]: self._layer("lower")   # one capital, like a phone keyboard
    def _erase(self):
        e=self._text["entry"]; e.set_text(e.get_text()[:-1])
    def _text_key(self,keyval):
        """With a key of the on-screen keyboard selected, a real keyboard still types into the text."""
        if keyval==Gdk.KEY_BackSpace: self._erase(); return True
        if keyval in (Gdk.KEY_Return,Gdk.KEY_KP_Enter): return False   # activates the selected key
        ch=Gdk.keyval_to_unicode(keyval)
        if ch>=32 and chr(ch).isprintable() and (not self._text["digits"] or chr(ch).isdigit()):
            e=self._text["entry"]; value=e.get_text()
            if not self._text["max"] or len(value)<self._text["max"]: e.set_text(value+chr(ch))
            return True
        return False
    def ask_search(self):
        """The search field typed with the on-screen keyboard (Enter on the empty search field)."""
        def done(text):
            self.search_entry.set_text(text); self.search_entry.grab_focus(); self.search_entry.set_position(-1)
        self.ask_text("Search",done,self.search_entry.get_text(),"Apps, channels, workspaces or window titles.",ok_label="Search")

    def choose_option(self,title,options,current,callback,back=None):
        """A small pop-up listing the choices for a setting, with the current one ticked. back() runs on Cancel."""
        self._begin_modal(); self._title(title); groups=[]; focus=None
        for key,label in options:
            chosen=key==current
            b=self.dialog_button("object-select-symbolic" if chosen else None,"✓" if chosen else "",label)
            b.connect("clicked",lambda _b,k=key:(self.close_modal(),callback(k))); self.modal_card.append(b); groups.append(NavGroup([b]))
            if chosen: focus=b
        cancelled=back or self.close_modal
        cancel=Gtk.Button(label="Cancel"); cancel.set_margin_top(S(8)); cancel.connect("clicked",lambda *_:cancelled()); self.modal_card.append(cancel); groups.append(NavGroup([cancel]))
        self._modal_groups=groups; self._modal_back=cancelled; (focus or groups[0][0]).grab_focus()

    def choose_profile(self,callback):
        """Pick an application: favorites first, then apps with channel numbers, then everything else."""
        self._begin_modal(); self._title("Choose an application")
        scroll=Gtk.ScrolledWindow(); scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC); scroll.set_max_content_height(S(380)); scroll.set_propagate_natural_height(True)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(2)); scroll.set_child(box); self.modal_card.append(scroll)
        groups=[]; apps=self.app.catalogue.by_id()
        for heading,profiles in startup_choices(self.app.store.profiles):
            box.append(section_title(heading))
            for p in profiles:
                a=apps.get(p.desktop_id); b=Gtk.Button(); b.add_css_class("launch-row")
                row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(10)); row.append(app_icon(a.icon if a else None,p.name,28))
                if p.channel is not None:
                    ch=Gtk.Label(label=f"{p.channel:03d}"); ch.add_css_class("channel-number"); row.append(ch)
                l=Gtk.Label(label=p.name); l.set_xalign(0); l.set_hexpand(True); l.set_ellipsize(3); row.append(l)
                detail=profile_detail(p,a)
                if detail:
                    d=Gtk.Label(label=detail); d.add_css_class("muted"); d.set_ellipsize(3); row.append(d)
                b.set_child(row); b.connect("clicked",lambda _b,prof=p:(self.close_modal(),callback(prof))); box.append(b); groups.append(NavGroup([b]))
        cancel=Gtk.Button(label="Cancel"); cancel.set_margin_top(S(8)); cancel.connect("clicked",lambda *_:self.close_modal()); self.modal_card.append(cancel); groups.append(NavGroup([cancel]))
        self._modal_groups=groups; self._modal_back=self.close_modal; groups[0][0].grab_focus()

    def assign_hotkey(self,owner,label,on_set,back=None):
        """Choose a hotkey for `owner` (("slot", device, action) or ("profile", id)) and pass it to on_set ("" clears it).
        A key that something else already has is only taken from it after a warning and a confirmation.
        back() runs instead of closing the dialog when it is cancelled."""
        store=self.app.store
        def got(spec):
            other=store.hotkey_owner(spec,owner) if spec else None
            if other is None: on_set(spec); return
            taken=store.owner_label(other)
            self.confirm("Hotkey already in use",f"{describe(spec)} is already the hotkey for “{taken}”. Use it for “{label}” instead? "
                         f"“{taken}” will no longer have a hotkey.","Use it here",lambda:on_set(spec),back=back)
        self.capture_hotkey(label,got,can_clear=True,cancelled=back)

    def show_app_hotkeys(self,changed=None):
        """The applications that have a hotkey: change or remove each one's. changed() runs after every change."""
        self._begin_modal(); self._title("Application hotkeys"); groups=[]
        again=lambda:self.show_app_hotkeys(changed)
        def set_key(profile_id,spec):
            self.app.set_profile_hotkey(profile_id,spec)
            if changed: changed()
            again()
        profiles=self.app.store.hotkey_profiles()
        if not profiles: self.modal_card.append(muted_label("No application has a hotkey yet. Give an app a hotkey with ✎ beside it in Applications."))
        scroll=Gtk.ScrolledWindow(); scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC); scroll.set_max_content_height(S(380)); scroll.set_propagate_natural_height(True)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4)); scroll.set_child(box); self.modal_card.append(scroll)
        apps=self.app.catalogue.by_id()
        for p in profiles:
            a=apps.get(p.desktop_id); row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(10))
            row.append(app_icon(a.icon if a else None,p.name,28))
            name=Gtk.Label(label=p.name); name.set_xalign(0); name.set_hexpand(True); name.set_ellipsize(3); row.append(name)
            key=Gtk.Label(label=describe(p.hotkey)); key.add_css_class("setting-value"); row.append(key)
            change=Gtk.Button(); change.add_css_class("square"); change.set_child(glyph("document-edit-symbolic","✎")); change.set_tooltip_text(f"Change the hotkey for {p.name}")
            change.connect("clicked",lambda _b,prof=p:self.assign_hotkey(("profile",prof.id),prof.name,lambda spec,pid=prof.id:set_key(pid,spec),back=again))
            remove=Gtk.Button(); remove.add_css_class("square"); remove.add_css_class("close-button"); remove.set_child(glyph("window-close-symbolic","✕")); remove.set_tooltip_text(f"Remove the hotkey for {p.name}")
            remove.connect("clicked",lambda _b,pid=p.id:set_key(pid,""))
            row.append(change); row.append(remove); box.append(row); groups.append(NavGroup([change,remove]))
        close=Gtk.Button(label="Close"); close.set_margin_top(S(8)); close.connect("clicked",lambda *_:self.close_modal()); self.modal_card.append(close); groups.append(NavGroup([close]))
        self._modal_groups=groups; self._modal_back=self.close_modal; groups[0][0].grab_focus()

    def capture_hotkey(self,label,callback,can_clear=False,cancelled=None):
        """Wait for a key or combination and pass its spec to callback; with can_clear, a Clear button passes "".
        cancelled() runs when it is cancelled instead of nothing."""
        self._begin_modal(); self._title("New hotkey"); self.modal_card.append(muted_label(f"Press the key or key combination for “{label}”.\nTap a modifier on its own (such as Super) to use it by itself. "
                                                                                   "The arrow keys and OK move to and press Cancel or Clear; Back cancels."))
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(6)); row.set_homogeneous(True); row.set_margin_top(S(14))
        cancel=Gtk.Button(label="Cancel"); cancel.connect("clicked",lambda *_:self._end_capture(None)); row.append(cancel); buttons=[cancel]
        if can_clear:
            clear=Gtk.Button(label="Clear"); clear.connect("clicked",lambda *_:self._end_capture("")); row.append(clear); buttons.append(clear)
        self.modal_card.append(row)
        self._modal_groups=[buttons]; self._modal_back=lambda:self._end_capture(None); self._capture=HotkeyCapture(); self._capture_cb=callback; self._capture_cancel=cancelled; cancel.grab_focus()
    def _capture_key(self,keyval,state):
        """True when the key was taken as (part of) the hotkey. The D-pad and OK keys on their own are not: they move
        between Cancel and Clear and press them (hotkeys.is_navigation)."""
        name=Gdk.keyval_name(keyval) or ""
        held=held_modifiers(state)
        if keyval in (Gdk.KEY_Escape,Gdk.KEY_Back) and not held: self._end_capture(None); return True
        if is_navigation(name,held): return False
        spec=self._capture.press(name,held)
        if spec: self._end_capture(spec)
        return True
    def _end_capture(self,spec):
        callback=self._capture_cb; cancelled=self._capture_cancel; self._capture=None; self._capture_cb=None; self._capture_cancel=None; self.close_modal()
        if spec is not None and callback: callback(spec)   # "" is Clear
        elif spec is None and cancelled: cancelled()
