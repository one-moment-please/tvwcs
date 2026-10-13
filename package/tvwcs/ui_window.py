"""The TVWCS window: Quick Menu | Applications (the applications guide, switchable to Settings),
remote-friendly navigation and modal dialogs."""
from __future__ import annotations
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk

from tvwcs.hotkeys import HotkeyCapture
from tvwcs.model import LAUNCH_NEW_WORKSPACE, LAUNCH_SAME, MAIN_TITLE, extract_badge, profile_detail, row_description, search_items, startup_choices
from tvwcs.theme import render_css
from tvwcs.ui_settings import build_settings_panel
from tvwcs.widgets import (NavGroup, S, app_icon, child_marker, clear_box, glyph, icon_button, icon_only, muted_label, section_title, usable)

APPS_VIEWS=("applications","settings")   # what the right-hand pane can show; it opens on the applications guide
FOCUS_TIP_DELAY=3000                     # ms a selected icon-only button waits before showing its tooltip (Settings > Button hints)
FOCUS_TIP_DURATION=6000                  # ms the tooltip then stays up

_TYPING_BLOCKED=Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.ALT_MASK|Gdk.ModifierType.SUPER_MASK|Gdk.ModifierType.META_MASK
_I3_MODS=((Gdk.ModifierType.SUPER_MASK,"Mod4"),(Gdk.ModifierType.ALT_MASK,"Mod1"),(Gdk.ModifierType.CONTROL_MASK,"Control"),(Gdk.ModifierType.SHIFT_MASK,"Shift"))

class TVWCSWindow(Gtk.ApplicationWindow):
    """One borderless window holding two panels side by side. The Quick Menu is always there; the
    Applications pane opens to its right on the applications guide, and a button at its top right switches it to Settings."""
    def __init__(self, app):
        super().__init__(application=app,title=MAIN_TITLE)
        self.app=app; self.guide_open=False; self.options_open=False
        self.guide_pane=None; self.options_pane=None; self.guide_scroll=None; self.guide_button=None; self.quick_content=None
        self.apps_stack=None; self.apps_view=APPS_VIEWS[0]; self.view_button=None; self.apps_title=None; self.apps_subtitle=None; self.settings_tab=None
        self._focus_tip=None; self._focus_tip_source=0
        self._provider=None; self._expanded={"Media","Internet","Games"}; self._guide_scroll=0.0
        self._popovers=0; self._was_active=False; self._capture=None; self._capture_cb=None; self._pin=None
        self._reset_nav()
        self.set_decorated(False); self.set_hide_on_close(True); self.set_resizable(True); self.add_css_class("tvwcs-window")
        key=Gtk.EventControllerKey(); key.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key.connect("key-pressed",self._key_pressed); key.connect("key-released",self._key_released); self.add_controller(key)
        self.connect("notify::focus-widget",self._focus_changed); self.connect("notify::is-active",self._active_changed)
        self._build()

    def _reset_nav(self):
        self._groups={"quick":[],"guide":[],"options":[]}; self._header_group=[]
        self._search_results=[]; self._selected_result=0; self._result_groups=[]; self._result_mains=[]; self._stars={}
        self._modal_groups=[]; self._modal_back=None; self._return_focus=None; self._last_focus={}; self._pin=None
        self._all_guide_groups=None; self._open_row=None

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
        self.modal_layer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL); self.modal_layer.add_css_class("modal-scrim"); self.modal_layer.set_visible(False)
        self.modal_card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(6)); self.modal_card.add_css_class("modal-card")
        self.modal_card.set_halign(Gtk.Align.CENTER); self.modal_card.set_valign(Gtk.Align.CENTER); self.modal_card.set_hexpand(True); self.modal_card.set_vexpand(True)
        self.modal_card.set_size_request(min(S(440),max(S(280),layout.quick_width-S(40))),-1)
        self.modal_layer.append(self.modal_card); overlay.add_overlay(self.modal_layer)
        self.set_child(overlay)
        self.set_panels(self.guide_open,self.options_open); self._refresh_search_results()

    def _install_css(self):
        display=Gdk.Display.get_default()
        if self._provider is None:
            self._provider=Gtk.CssProvider()
            if display: Gtk.StyleContext.add_provider_for_display(display,self._provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._provider.load_from_data(render_css(self.app.store.settings["accent"],self.app.scale_factor).encode("utf-8"))

    def set_panels(self,guide,options=None):
        """Show or hide the Applications pane. It holds the applications guide and Settings, built once and kept,
        so switching between them never disturbs scroll positions, open categories or focus. Opening it always
        starts on the applications guide. `options` is accepted for older callers but opens nothing separate."""
        guide=bool(guide); opening=guide and not self.guide_open
        self.guide_open=guide; self.options_open=False
        if opening: self.apps_view="applications"
        if guide and self.guide_pane is None: self.guide_pane=self._build_guide_pane(); self.panes.append(self.guide_pane)
        elif opening: self.show_applications_view("applications")
        layout=self.app.layout
        self.quick_pane.set_size_request(layout.quick_width,-1)
        if self.guide_pane is not None: self.guide_pane.set_visible(guide)
        if self.guide_button is not None:
            (self.guide_button.add_css_class if guide else self.guide_button.remove_css_class)("active")
            self.guide_button.set_tooltip_text("Hide the applications window" if guide else "Open the applications window (+)")

    def _build_quick_pane(self,width):
        pane=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0); pane.add_css_class("pane"); pane.set_size_request(width,-1); pane.set_hexpand(False)
        header=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(10)); header.set_margin_top(S(14)); header.set_margin_start(S(20)); header.set_margin_end(S(20)); header.set_margin_bottom(S(10))
        title=Gtk.Label(label="TVWCS"); title.add_css_class("brand"); title.set_xalign(0); title.set_hexpand(True); header.append(title)
        controls=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=0); controls.add_css_class("window-controls")
        close_btn=icon_button("window-close-symbolic","✕","Close"); close_btn.add_css_class("close-button"); close_btn.add_css_class("square"); close_btn.connect("clicked",lambda *_:self.app.hide_window()); controls.append(close_btn)
        header.append(controls)   # the ✕ sits left of the applications button, whose right edge lines up with the search field
        guide_btn=Gtk.Button(); guide_btn.add_css_class("square"); guide_btn.set_child(glyph("open-menu-symbolic","☰")); guide_btn.set_tooltip_text("Open the applications window (+)"); guide_btn.connect("clicked",lambda *_:self.app.show_mode("guide")); header.append(guide_btn); self.guide_button=guide_btn
        pane.append(header); self._header_group=[close_btn,guide_btn]   # focus order matches left-to-right layout
        body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(10)); body.set_margin_start(S(20)); body.set_margin_end(S(20)); body.set_margin_top(S(4)); body.set_vexpand(True); pane.append(body)
        self.search_entry=Gtk.SearchEntry(); self.search_entry.set_placeholder_text("Type to search apps, channels, workspaces…"); self.search_entry.connect("search-changed",lambda *_:self._refresh_search_results()); self.search_entry.connect("activate",self._activate_search); body.append(self.search_entry)
        self.results_scroll=Gtk.ScrolledWindow(); self.results_scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC); self.results_scroll.set_max_content_height(S(280)); self.results_scroll.set_propagate_natural_height(True); self.results_scroll.set_visible(False)
        self.results_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(2)); self.results_scroll.set_child(self.results_box); body.append(self.results_scroll)
        scroll=Gtk.ScrolledWindow(); scroll.set_vexpand(True); scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC); body.append(scroll)
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4)); scroll.set_child(content); self.quick_content=content
        self._build_quick_content(content)
        footer=Gtk.Label(label="↑ ↓ ← →  Navigate    Enter  Select    Esc  Back    Just type to search"); footer.add_css_class("muted"); footer.set_xalign(0); footer.set_wrap(True)
        footer.set_margin_start(S(20)); footer.set_margin_end(S(20)); footer.set_margin_top(S(8)); footer.set_margin_bottom(S(12)); pane.append(footer)
        return pane

    def _build_quick_content(self,content):
        content.append(section_title("OPEN APPLICATIONS"))
        entries=self.app.workspace_entries(); outputs=self.app.wm.outputs()
        if not entries: content.append(muted_label("No open application windows detected, or i3-msg is unavailable."))
        for entry in entries:
            content.append(self._window_row(entry.windows[0]) if len(entry.windows)==1 else self._workspace_row(entry,outputs))
        content.append(section_title("FAVORITES"))
        favorites=self.app.store.favorites()
        if not favorites: content.append(muted_label("No favorites yet. Open the Guide and use ☆ to pin an item here."))
        for profile in favorites: content.append(self._favorite_row(profile))

    # ---------------------------------------------------------- Quick Menu rows
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
        row,group=self._options_row(main,[self._mode_button(p),self._actions_button(app)])
        self._groups["quick"].append(group); return row

    def _window_row(self,w,nested=False):
        """An application on a workspace of its own (or one app inside an expanded workspace)."""
        title,badge=extract_badge(w["title"],w.get("urgent",False))
        app=self.app.match_application_window(w)
        main=Gtk.Button(); main.add_css_class("launch-row"); main.set_hexpand(True)
        inner=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(12)); inner.append(self.app.window_icon(w,32,badge))
        label=Gtk.Label(label=title); label.set_xalign(0); label.set_hexpand(True); label.set_ellipsize(3); inner.append(label); main.set_child(inner)
        main.connect("clicked",lambda _b,con=w["con_id"]:self.app.focus_window(con))
        row,group=self._options_row(main,[self._other_way_button(w),self._actions_button(app),self._close_button(w["con_id"])])
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
        move=None
        if others:   # only offered when there is somewhere else to send it
            move=icon_button("video-display-symbolic","▭","Move this workspace to another monitor")
            move.connect("clicked",lambda _b,e=entry,anchor=move,o=others:self._show_monitors(e,o,anchor))
        children=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(2)); children.set_visible(False)
        expand=Gtk.Button()
        def style(opened):
            expand.set_child(glyph("pan-up-symbolic" if opened else "pan-down-symbolic","▴" if opened else "▾"))
            expand.set_tooltip_text("Hide the individual apps" if opened else "Show the individual apps, to open just one")
        def flip(*_):
            show=not children.get_visible(); children.set_visible(show); style(show)
        style(False); expand.connect("clicked",flip)
        close=icon_button("window-close-symbolic","✕","Close this workspace and every app on it"); close.add_css_class("close-button")
        close.connect("clicked",lambda _b,e=entry:self.confirm("Close workspace?",f"Close {e.label} and its {len(e.windows)} applications? Unsaved work in them may be lost.","Close workspace",lambda:self.app.close_workspace(e)))
        row,group=self._options_row(main,[move,expand,close])
        self._groups["quick"].append(group)          # registered before its children so navigation order is top to bottom
        for w in entry.windows: children.append(self._window_row(w,nested=True))
        box.append(row); box.append(children); return box

    def _options_row(self,main,options):
        """Quick Menu rows mirror the Applications list: the application is on the right, its options on the left
        behind one button that expands them in place. Pressing ← while the application is selected (or right-clicking
        it) opens those options too, so they can be reached even when the ☰ button is hidden in Settings. The options
        fold away again as soon as the selection leaves them (see _focus_changed)."""
        options=[o for o in options if o is not None]
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(4))
        if not options:
            row.append(main); return row,NavGroup([main],entry=main)
        for b in options: b.add_css_class("square")
        hide=self.app.store.settings.get("hide_options_buttons",False)
        toggle=Gtk.Button(); toggle.add_css_class("options-toggle"); toggle.add_css_class("square"); toggle.set_visible(not hide)
        opts=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(4)); opts.set_visible(False)
        for b in options: opts.append(b)
        group=NavGroup([toggle,*options,main],entry=main); group.toggle=toggle if not hide else None
        def style(expanded):
            toggle.set_child(glyph("go-previous-symbolic","‹") if expanded else glyph("open-menu-symbolic","☰"))
            toggle.set_tooltip_text("Hide options" if expanded else "Options")
            (toggle.add_css_class if expanded else toggle.remove_css_class)("active")
        def show(visible):
            opts.set_visible(visible); style(visible)
            if visible:
                previous=self._open_row; self._open_row=group
                if previous is not None and previous is not group and previous.expanded(): previous.collapse()   # one open row at a time
        def flip(*_): show(not opts.get_visible())
        def open_options(*_):
            if not opts.get_visible(): show(True); options[-1].grab_focus()   # the option right next to the application
            return True
        style(False); toggle.connect("clicked",flip)
        click=Gtk.GestureClick(); click.set_button(3); click.connect("pressed",lambda *_a:open_options()); main.add_controller(click)
        row.append(toggle); row.append(opts); row.append(main)
        group.expanded=opts.get_visible; group.expand=lambda:show(True); group.collapse=lambda:show(False)
        group.open_options=open_options; group.menu=[toggle,*options]
        return row,group

    @staticmethod
    def _lock_mark():
        mark=glyph("changes-prevent-symbolic","🔒",16); mark.set_tooltip_text("Protected by a PIN"); return mark

    def _mode_button(self,p):
        """Persistent per-profile setting: always launch in a new workspace, or tiled in the current one."""
        b=Gtk.Button(); b.add_css_class("mode-button"); b.add_css_class("square"); self._style_mode_button(b,p.launch_mode)
        b.connect("clicked",lambda _b,pid=p.id:self._toggle_mode(pid,_b)); return b
    def _style_mode_button(self,b,mode):
        if mode==LAUNCH_NEW_WORKSPACE:
            b.set_child(glyph("view-fullscreen-symbolic","▣")); b.set_tooltip_text("Launches in its own new workspace, hiding other apps. Click to launch tiled in the current workspace instead.")
        else:
            b.set_child(glyph("view-dual-symbolic","◫")); b.set_tooltip_text("Launches tiled in the current workspace. Click to launch in its own new workspace instead.")
    def _toggle_mode(self,profile_id,button):
        mode=self.app.store.toggle_launch_mode(profile_id)
        if mode: self._style_mode_button(button,mode)

    def _other_way_button(self,w):
        """Open this running app the opposite way to the current default: tiled here, or in a workspace of its own."""
        alt=LAUNCH_SAME if self.app.window_mode(w)==LAUNCH_NEW_WORKSPACE else LAUNCH_NEW_WORKSPACE
        if alt==LAUNCH_SAME: b=icon_button("view-dual-symbolic","◫","Open as a tile in the current workspace, next to the other apps")
        else: b=icon_button("view-fullscreen-symbolic","▣","Open in a new workspace of its own")
        b.connect("clicked",lambda _b,con=w["con_id"],mode=alt:self.app.focus_window(con,mode)); return b
    def _actions_button(self,app):
        if not app or not app.desktop_actions: return None
        b=icon_button("view-list-symbolic","☰","Desktop actions"); b.connect("clicked",lambda _b,a=app,anchor=b:self._show_actions(a,anchor)); return b
    def _close_button(self,con_id):
        b=icon_button("window-close-symbolic","✕","Close this application"); b.add_css_class("close-button"); b.connect("clicked",lambda _b,con=con_id:self._close_open_window(con)); return b

    def _popup(self,anchor,child):
        pop=Gtk.Popover(); pop.set_parent(anchor); pop.set_child(child); self._popovers+=1
        def closed(p): self._popovers=max(0,self._popovers-1); GLib.idle_add(p.unparent)
        pop.connect("closed",closed)
        key=Gtk.EventControllerKey(); key.connect("key-pressed",lambda _c,kv,_kc,_st:(pop.popdown(),True)[1] if kv==Gdk.KEY_Back else False); pop.add_controller(key)
        pop.popup(); return pop
    def _show_actions(self,app,anchor):
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4)); holder=[]
        for action_id,action_name in app.desktop_actions:
            b=Gtk.Button(label=action_name); b.set_halign(Gtk.Align.FILL); b.connect("clicked",lambda _b,a=app,aid=action_id:(holder[0].popdown(),self.app.launch_action(a,aid))); box.append(b)
        holder.append(self._popup(anchor,box))
    def _show_monitors(self,entry,outputs,anchor):
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4)); holder=[]
        box.append(muted_label("Move to monitor"))
        for name in outputs:
            b=Gtk.Button(label=name); b.set_halign(Gtk.Align.FILL); b.connect("clicked",lambda _b,n=name:(holder[0].popdown(),self.app.move_workspace(entry.name,n))); box.append(b)
        holder.append(self._popup(anchor,box))
    def _close_open_window(self,con_id):
        if not self.app.wm.close_window(con_id): self.app.notify_message("Could not close that application window.")
        GLib.timeout_add(250,lambda:(self.app.refresh_data(rebuild=True),GLib.SOURCE_REMOVE)[1])

    # ---------------------------------------------------------- Applications pane (guide | Settings)
    def _build_guide_pane(self):
        """The Applications pane: a header (title, and at the top right a button that switches between the
        applications guide and Settings) over a stack of the two. Its focusable widgets register into pane "guide"."""
        margin=self.app.layout.margin
        pane=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0); pane.add_css_class("pane"); pane.set_hexpand(True); pane.set_margin_start(margin)
        head=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(14)); head.set_margin_top(S(12)); head.set_margin_start(S(24)); head.set_margin_end(S(24)); head.set_margin_bottom(S(2))
        self.apps_title=Gtk.Label(); self.apps_title.add_css_class("pane-title"); self.apps_title.set_xalign(0); head.append(self.apps_title)
        self.apps_subtitle=Gtk.Label(); self.apps_subtitle.add_css_class("muted"); self.apps_subtitle.set_valign(Gtk.Align.END); self.apps_subtitle.set_margin_bottom(S(4)); self.apps_subtitle.set_xalign(0); head.append(self.apps_subtitle)
        spacer=Gtk.Box(); spacer.set_hexpand(True); head.append(spacer)   # keeps the switch button at the top right in both views
        self.view_button=Gtk.Button(); self.view_button.set_valign(Gtk.Align.START)
        self.view_button.connect("clicked",lambda *_:self.show_applications_view("settings" if self.apps_view=="applications" else "applications"))
        head.append(self.view_button); self._register("guide",self.view_button)
        pane.append(head)
        self.apps_stack=Gtk.Stack(); self.apps_stack.set_vexpand(True); self.apps_stack.set_hexpand(True); self.apps_stack.set_transition_type(Gtk.StackTransitionType.NONE)
        pane.append(self.apps_stack)
        self.apps_list_scroll=Gtk.ScrolledWindow(); self.apps_list_scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        self.apps_content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4)); self.apps_content.set_margin_start(S(24)); self.apps_content.set_margin_end(S(24)); self.apps_content.set_margin_bottom(S(16))
        self.apps_list_scroll.set_child(self.apps_content); self.apps_stack.add_named(self.apps_list_scroll,"applications")
        self.settings_tab=build_settings_panel(self,embedded=True); self.apps_stack.add_named(self.settings_tab,"settings")
        self._rebuild_apps_content()
        self._all_guide_groups=list(self._groups["guide"])   # both views; _sync_view_groups picks the visible one's
        self.show_applications_view(self.apps_view)
        return pane

    def show_applications_view(self,key):
        """Show the applications guide or Settings in the Applications pane, and keep only the visible one's nav groups live."""
        if key not in APPS_VIEWS: key="applications"
        self.apps_view=key
        if self.apps_stack is not None: self.apps_stack.set_visible_child_name(key)
        settings=key=="settings"
        if self.apps_title is not None: self.apps_title.set_text("Settings" if settings else "Applications")
        if self.apps_subtitle is not None: self.apps_subtitle.set_visible(not settings)
        if self.view_button is not None:
            self.view_button.set_child(glyph("view-grid-symbolic","▦") if settings else glyph("emblem-system-symbolic","⚙"))
            self.view_button.set_tooltip_text("Back to the applications guide" if settings else "Settings")
            (self.view_button.add_css_class if settings else self.view_button.remove_css_class)("active")
            if self.get_focus() is self.view_button: self._schedule_focus_tip(self.view_button)   # its tooltip just changed
        self._sync_view_groups()
        return True

    def _sync_view_groups(self):
        """Keep only the header button and the visible view's widgets in pane "guide". The hidden view stays in the
        Gtk.Stack, so its rows must not take part in ←/→/↑/↓ navigation."""
        groups=getattr(self,"_all_guide_groups",None)
        if groups is None: return
        visible=self.apps_stack.get_visible_child() if self.apps_stack is not None else None
        kept=[]
        for g in groups:
            root=getattr(g,"entry",None) or next(iter(g),None)
            if root is None: continue
            owner=next((r for r in (self.apps_list_scroll,self.settings_tab) if r is not None and (root is r or root.is_ancestor(r))),None)
            if owner is None or owner is visible: kept.append(g)
        self._groups["guide"]=kept

    def _rebuild_apps_content(self):
        """The applications guide: your channels, then every installed application by category."""
        clear_box(self.apps_content)
        assigned=self.app.store.assigned()
        if self.apps_subtitle is not None: self.apps_subtitle.set_text(f"{len(assigned)} channels assigned")
        self.guide_scroll=self.apps_list_scroll
        self.apps_content.append(section_title("CHANNEL GUIDE"))
        if not assigned: self.apps_content.append(muted_label("Assign channel numbers to launch profiles to build your own lineup."))
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
        ch=Gtk.Label(label=f"{p.channel:03d}" if p.channel is not None else "—"); ch.set_width_chars(4); ch.set_xalign(0); ch.add_css_class("channel-number"); inner.append(ch)
        name=Gtk.Label(label=p.name); name.set_xalign(0); name.set_ellipsize(3); inner.append(name)
        # A main profile shows its application's description, a secondary one its launch options; either can be overridden in the editors.
        description=row_description(p,app,primary,self.app.store.app_descriptions.get(p.desktop_id,""))
        if description:
            name.set_max_width_chars(32)
            if p.pin_hash: inner.append(self._lock_mark())
            d=Gtk.Label(label=description); d.add_css_class("description"); d.set_xalign(0); d.set_hexpand(True); d.set_ellipsize(3); inner.append(d)
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

    def _style_star(self,button,favorite):
        button.set_child(glyph("starred-symbolic" if favorite else "non-starred-symbolic","★" if favorite else "☆"))
        button.set_tooltip_text("Remove favorite" if favorite else "Add to favorites")
    def refresh_favorites(self,profile_id):
        """A favorite changed: restyle its star(s) and rebuild only the Quick Menu list; the Guide stays put."""
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
        if not q.strip(): self._search_results=[]; return
        self._search_results=search_items(q,self.app.store.profiles,self.app.catalogue.by_id(),self.app.wm.windows())[:12]
        if not self._search_results:
            self.results_box.append(muted_label("No matches. Try an app name, profile name, channel number, or window title.")); return
        for i,result in enumerate(self._search_results):
            main=Gtk.Button(); main.add_css_class("launch-row"); main.set_hexpand(True)
            row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(10))
            if result["kind"]=="window":
                w=result["window"]; row.append(self.app.window_icon(w,28,result.get("badge"))); app=self.app.match_application_window(w)
                options=[self._other_way_button(w),self._actions_button(app),self._close_button(w["con_id"])]
            else:
                p=result["profile"]; app=self.app.catalogue.by_id().get(p.desktop_id); row.append(app_icon(app.icon if app else None,p.name,28))
                options=[self._mode_button(p),self._actions_button(app)]
            label=Gtk.Label(label=result["label"]); label.set_xalign(0); label.set_hexpand(True); label.set_ellipsize(3); row.append(label)
            detail=Gtk.Label(label=result["detail"]); detail.add_css_class("muted"); detail.set_ellipsize(3); row.append(detail); main.set_child(row)
            if i==self._selected_result: main.add_css_class("tvwcs-selected")
            main.connect("clicked",lambda _b,r=result:self.app.activate_result(r))
            line,group=self._options_row(main,options); self._result_groups.append(group); self._result_mains.append(main); self.results_box.append(line)
    def _activate_search(self,*_):
        q=self.search_entry.get_text().strip()
        if q.isdigit():
            p=next((p for p in self.app.store.profiles if p.channel==int(q)),None)
            if p: self.app.launch_profile(p); return
        if self._search_results: self.app.activate_result(self._search_results[self._selected_result])
    def _select_result(self,index):
        self._selected_result=index
        for i,b in enumerate(self._result_mains):
            b.remove_css_class("tvwcs-selected")
            if i==index: b.add_css_class("tvwcs-selected")
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
        hovered=button.get_state_flags() & Gtk.StateFlags.PRELIGHT   # the pointer is on it: GTK's own tooltip is showing
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
        return [self._header_group,[self.search_entry]]+list(self._result_groups)+list(self._groups["quick"])
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
                if not group.expanded(): group.expand(); return True   # Left on the options button opens the options
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
        if self._capture is not None: return self._capture_key(keyval,state)
        self._hide_focus_tip()   # any key press dismisses it; the next selection schedules a fresh one
        focused=self.get_focus(); editable=isinstance(focused,Gtk.Editable); typing=self._in_search(focused)
        if keyval in (Gdk.KEY_Escape,Gdk.KEY_Back): self._escape(); return True   # the remote's Back key (XF86Back) is Esc
        if self._pin is not None and self._pin_key(keyval): return True
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
            g=self._result_groups[self._selected_result]   # at the end of the text, Right reaches the highlighted result's options
            if g.expand and g.toggle is not None: g.expand(); g.toggle.grab_focus(); return True
        if keyval in (Gdk.KEY_Left,Gdk.KEY_Right) and not editable:
            if self._move_within_group(1 if keyval==Gdk.KEY_Right else -1): return True
        if keyval in (Gdk.KEY_Return,Gdk.KEY_KP_Enter) and typing: self._activate_search(); return True
        return False
    def _key_released(self,_controller,keyval,_keycode,state):
        if self._capture is not None:
            spec=self._capture.release(Gdk.keyval_name(keyval))
            if spec: self._end_capture(spec)
    def _escape(self):
        if self._modal_groups: (self._modal_back or self.close_modal)(); return
        if self.options_open: self.app.show_panels(True,False,focus="guide"); return   # Back: close Settings, keep the Guide
        if self.guide_open and self.apps_view=="settings":                               # Settings goes back to the guide
            self.show_applications_view("applications"); self.view_button.grab_focus(); return
        if self.guide_open: self.app.show_panels(False,False,focus="quick"); return    # then the Guide, keep the Quick Menu
        self.app.hide_window()

    # ---------------------------------------------------------- close when focus leaves
    def _active_changed(self,*_):
        if self.is_active(): self._was_active=True; return
        if self._was_active and self.is_visible() and self.app.store.settings["close_on_click_outside"]:
            GLib.timeout_add(150,self._close_if_unfocused)
    def _close_if_unfocused(self):
        # Child windows (profile editor) and open popovers legitimately take focus; only a click elsewhere closes TVWCS.
        if self.is_visible() and not self.is_active() and self._popovers==0 and not self.app.has_dialogs(): self.app.hide_window()
        return GLib.SOURCE_REMOVE
    def note_shown(self): self._was_active=False; self._hide_focus_tip()

    # ---------------------------------------------------------- dialogs (drawn over the panels, remote-navigable)
    def _begin_modal(self):
        if not self._modal_groups: self._return_focus=self.get_focus()
        clear_box(self.modal_card); self.modal_layer.set_visible(True)
    def close_modal(self):
        self._modal_groups=[]; self._modal_back=None; self.modal_layer.set_visible(False); self._capture=None; self._pin=None
        back=self._return_focus
        if back is not None and usable(back): back.grab_focus()
        else: self.focus_pane("quick")
    def _title(self,text):
        t=Gtk.Label(label=text); t.add_css_class("pane-title"); t.set_xalign(0); t.set_wrap(True); t.set_margin_bottom(S(8)); self.modal_card.append(t)
    def dialog_button(self,icon,fallback,text):
        b=Gtk.Button(); b.add_css_class("dialog-button"); row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(14))
        g=glyph(icon,fallback,24) if icon else Gtk.Label(); g.set_size_request(S(28),-1); row.append(g)
        l=Gtk.Label(label=text); l.set_xalign(0); l.set_hexpand(True); row.append(l); b.set_child(row); return b

    def confirm(self,title,message,label,on_confirm,back=None):
        """Ask before doing something destructive. Cancel is focused, so a stray Enter is harmless."""
        self._begin_modal(); self._title(title)
        text=muted_label(message); text.set_margin_bottom(S(14)); self.modal_card.append(text)
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(6)); row.set_homogeneous(True)
        cancel=Gtk.Button(label="Cancel"); cancel.connect("clicked",lambda *_:(back or self.close_modal)()); row.append(cancel)
        go=Gtk.Button(label=label); go.add_css_class("danger"); go.connect("clicked",lambda *_:(self.close_modal(),on_confirm())); row.append(go)
        self.modal_card.append(row); self._modal_groups=[[cancel,go]]; self._modal_back=back or self.close_modal; cancel.grab_focus()

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

    def choose_option(self,title,options,current,callback):
        """A small pop-up listing the choices for a setting, with the current one ticked."""
        self._begin_modal(); self._title(title); groups=[]; focus=None
        for key,label in options:
            chosen=key==current
            b=self.dialog_button("object-select-symbolic" if chosen else None,"✓" if chosen else "",label)
            b.connect("clicked",lambda _b,k=key:(self.close_modal(),callback(k))); self.modal_card.append(b); groups.append(NavGroup([b]))
            if chosen: focus=b
        self._modal_groups=groups; self._modal_back=self.close_modal; (focus or groups[0][0]).grab_focus()

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

    def capture_hotkey(self,label,callback,can_clear=False):
        """Wait for a key or combination and pass its spec to callback; with can_clear, a Clear button passes ""."""
        self._begin_modal(); self._title("New hotkey"); self.modal_card.append(muted_label(f"Press the key or key combination for “{label}”.\nTap a modifier on its own (such as Super) to use it by itself. Esc cancels."))
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(6)); row.set_homogeneous(True); row.set_margin_top(S(14))
        cancel=Gtk.Button(label="Cancel"); cancel.connect("clicked",lambda *_:self._end_capture(None)); row.append(cancel); buttons=[cancel]
        if can_clear:
            clear=Gtk.Button(label="Clear"); clear.connect("clicked",lambda *_:self._end_capture("")); row.append(clear); buttons.append(clear)
        self.modal_card.append(row)
        self._modal_groups=[buttons]; self._modal_back=lambda:self._end_capture(None); self._capture=HotkeyCapture(); self._capture_cb=callback; cancel.grab_focus()
    def _capture_key(self,keyval,state):
        name=Gdk.keyval_name(keyval) or ""
        held=[m for mask,m in _I3_MODS if state & mask]
        if keyval in (Gdk.KEY_Escape,Gdk.KEY_Back) and not held: self._end_capture(None); return True
        spec=self._capture.press(name,held)
        if spec: self._end_capture(spec)
        return True
    def _end_capture(self,spec):
        callback=self._capture_cb; self._capture=None; self._capture_cb=None; self.close_modal()
        if spec is not None and callback: callback(spec)   # "" is Clear
