"""Small GTK helpers shared by the TVWCS windows: scaling, icons, navigation groups."""
from __future__ import annotations
import os
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, Gio, GLib, Graphene, Gtk

METRO_COLORS=("#0078d7","#e81123","#00b294","#ff8c00","#881798","#107c10","#ea005e","#6b69d6","#00cc6a","#c239b3")
_scale=[1.0]

_I3_MODS=((Gdk.ModifierType.SUPER_MASK,"Mod4"),(Gdk.ModifierType.ALT_MASK,"Mod1"),(Gdk.ModifierType.CONTROL_MASK,"Control"),(Gdk.ModifierType.SHIFT_MASK,"Shift"))

def held_modifiers(state):
    """The i3 names of the modifiers held in a key event's state, for hotkeys.HotkeyCapture."""
    return [m for mask,m in _I3_MODS if state & mask]

def set_scale(factor): _scale[0]=float(factor)
def S(n):
    """Scale a desktop-size pixel measure by the current interface size."""
    return 0 if n<=0 else max(1,round(n*_scale[0]))

def _theme():
    display=Gdk.Display.get_default()
    return Gtk.IconTheme.get_for_display(display) if display else None

def has_icon(name):
    theme=_theme()
    return bool(name and theme and theme.has_icon(name))

def glyph(icon_name, fallback, size=None):
    """A symbolic icon if the icon theme has it, otherwise a text glyph."""
    if has_icon(icon_name):
        img=Gtk.Image.new_from_icon_name(icon_name)
        if size: img.set_pixel_size(S(size))
    else: img=Gtk.Label(label=fallback)
    img.add_css_class("glyph"); return img   # marks the button holding it as icon-only (see icon_only)

def icon_button(icon_name, fallback, tooltip):
    b=Gtk.Button(); b.set_child(glyph(icon_name,fallback)); b.set_tooltip_text(tooltip); return b

def letter_tile(label, size):
    text=((label or "?").strip()[:1] or "?").upper()
    tile=Gtk.Label(label=text); tile.set_size_request(S(size),S(size)); tile.add_css_class("icon-tile")
    tile.add_css_class(f"tile-{sum(ord(c) for c in (label or '?'))%len(METRO_COLORS)}")
    tile.set_halign(Gtk.Align.CENTER); tile.set_valign(Gtk.Align.CENTER); return tile

def app_icon(spec, label, size=32, badge=None):
    """Application logo (theme icon or file), else a coloured letter tile; optional badge overlay."""
    widget=None
    if spec:
        if os.path.isabs(spec) and os.path.exists(spec):
            widget=Gtk.Image.new_from_gicon(Gio.FileIcon.new(Gio.File.new_for_path(spec))); widget.set_pixel_size(S(size))
        elif has_icon(spec):
            widget=Gtk.Image.new_from_icon_name(spec); widget.set_pixel_size(S(size))
    if widget is None: widget=letter_tile(label,size)
    widget.set_halign(Gtk.Align.CENTER); widget.set_valign(Gtk.Align.CENTER)
    if not badge: return widget
    overlay=Gtk.Overlay(); overlay.set_child(widget); overlay.set_size_request(S(size),S(size))
    chip=Gtk.Label(label=badge); chip.add_css_class("badge"); chip.set_halign(Gtk.Align.END); chip.set_valign(Gtk.Align.START)
    overlay.add_overlay(chip); return overlay

def child_marker(size=32):
    """The mark that stands in for a logo on a secondary profile: it hangs from the application above it."""
    mark=Gtk.Label(label="↳"); mark.add_css_class("child-marker"); mark.set_size_request(S(size),-1)
    mark.set_halign(Gtk.Align.CENTER); mark.set_valign(Gtk.Align.CENTER); return mark

def clear_box(box):
    child=box.get_first_child()
    while child:
        nxt=child.get_next_sibling(); box.remove(child); child=nxt

def muted_label(text):
    l=Gtk.Label(label=text); l.set_xalign(0); l.set_wrap(True); l.add_css_class("muted"); return l

def section_title(text):
    l=Gtk.Label(label=text); l.add_css_class("section-title"); l.set_xalign(0); return l

def icon_only(w):
    """A button whose only content is a glyph: it has no words, so its tooltip is its label."""
    get_child=getattr(w,"get_child",None); child=get_child() if get_child else None
    return bool(child is not None and child.has_css_class("glyph") and w.get_tooltip_text())

def _content(scroll):
    """What a ScrolledWindow scrolls: a plain box is wrapped in a Viewport, whose own coordinates move with the scrolling."""
    child=scroll.get_child()
    return child.get_child() if isinstance(child,Gtk.Viewport) and child.get_child() is not None else child

def scroll_to_show(scroll, widget):
    """Scroll as little as needed for the widget to be wholly in sight (the tabs: moving down them never jumps)."""
    ok,point=widget.compute_point(_content(scroll),Graphene.Point())
    if not ok: return
    adj=scroll.get_vadjustment(); top=point.y; bottom=top+widget.get_height(); value=adj.get_value()
    if top<value: adj.set_value(max(adj.get_lower(),top))
    elif bottom>value+adj.get_page_size(): adj.set_value(min(adj.get_upper()-adj.get_page_size(),bottom-adj.get_page_size()))

def scroll_into_view(scroll, widget):
    """Scroll so the widget is in the middle of the ScrolledWindow: focusing a row before the list has its size
    does not scroll to it by itself, so the current choice of a long list would start out of sight."""
    ok,point=widget.compute_point(_content(scroll),Graphene.Point())
    if not ok: return
    adj=scroll.get_vadjustment(); middle=point.y+widget.get_height()/2-adj.get_page_size()/2
    adj.set_value(max(adj.get_lower(),min(middle,adj.get_upper()-adj.get_page_size())))

class Marquee(Gtk.ScrolledWindow):
    """A one-line text that ends in … when it does not fit. While `run()` is on (its row is selected) the whole text
    scrolls past slowly, then starts over; `truncated` says whether it is cut, for a tooltip with all of it."""
    STEP_MS=30; PAUSE_MS=1400
    def __init__(self, text, css=None):
        super().__init__(); self.set_policy(Gtk.PolicyType.EXTERNAL,Gtk.PolicyType.NEVER); self.set_hexpand(True)
        self.set_can_focus(False); self.set_can_target(False); self.set_valign(Gtk.Align.CENTER)
        self.label=Gtk.Label(label=text); self.label.set_xalign(0); self.label.set_ellipsize(3)
        if css: self.label.add_css_class(css)
        self.set_child(self.label); self.source=0; self.text=text
    @property
    def truncated(self):
        return self.source!=0 or self.label.get_layout().is_ellipsized()
    def run(self, on):
        if on and self.source==0 and self.label.get_layout().is_ellipsized():
            self.label.set_ellipsize(0); self.source=GLib.timeout_add(self.PAUSE_MS,self._step)
        elif not on and self.source:
            GLib.source_remove(self.source); self.source=0; self.label.set_ellipsize(3); self.get_hadjustment().set_value(0)
    def _step(self):
        """One step to the left; at the end it holds, jumps back to the start and holds again. Each step schedules the next."""
        adj=self.get_hadjustment(); end=adj.get_upper()-adj.get_page_size()
        if adj.get_value()>=end: adj.set_value(0); wait=self.PAUSE_MS
        else:
            adj.set_value(min(end,adj.get_value()+S(2))); wait=self.PAUSE_MS if adj.get_value()>=end else self.STEP_MS
        self.source=GLib.timeout_add(wait,self._step); return GLib.SOURCE_REMOVE

def usable(w): return w.get_visible() and w.get_mapped() and w.get_sensitive()

class NavGroup(list):
    """Controls on one row, reached with Left/Right. Up/Down lands on `entry` (the row's main control).
    Rows whose options fold away have `toggle` (the options button) plus `expand` and `expanded`."""
    def __init__(self,widgets=(),entry=None):
        super().__init__(widgets); self.entry=entry; self.toggle=None; self.expand=None; self.expanded=None; self.column=False   # column: a grid row, Up/Down keeps the column
        self.lead=None   # a Quick Menu row's first button after ⋯ when it is not `entry`: ← on entry moves to it, ← on it opens the menu
        self.lane=None   # in a multi-column layout (Settings), which column the row is in; ←/→ jump between lanes

def screen_height():
    """The tallest connected monitor's height in logical pixels (0 when there is no display yet)."""
    display=Gdk.Display.get_default()
    if display is None: return 0
    monitors=display.get_monitors(); best=0
    for i in range(monitors.get_n_items()):
        best=max(best,monitors.get_item(i).get_geometry().height)
    return best

class PointerWatch:
    """Marks a window with the "pointer" CSS class while the mouse is really being used, so hover colours (theme.py)
    show only then. The pointer may be hidden after a few seconds without moving (cursor.py), but GTK still counts it
    as over whatever it rests on: without this, that row would look half-selected next to the remote's real
    selection. A key press, or the hiding time without moving, takes the class away; the first event after the window
    appears under a resting pointer does not count as moving. `idle_ms` gives the hiding time in ms (None when the
    pointer is never hidden: then only a key press takes hover away)."""
    IDLE_MS=3000
    MIN_MOVE=3   # pixels
    def __init__(self, window, idle_ms=None):
        self.window=window; self.last=None; self.source=0; self.idle_ms=idle_ms or (lambda:self.IDLE_MS)
        motion=Gtk.EventControllerMotion(); motion.connect("enter",self._enter); motion.connect("motion",self._moved)
        motion.connect("leave",lambda *_:self.off()); window.add_controller(motion)
        key=Gtk.EventControllerKey(); key.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key.connect("key-pressed",lambda *_:(self.off(),False)[1]); window.add_controller(key)
    @property
    def active(self): return self.window.has_css_class("pointer")
    def _enter(self, _c, x, y): self.last=(x,y)
    def _moved(self, _c, x, y):
        last=self.last; self.last=(x,y)
        if last is None or abs(x-last[0])+abs(y-last[1])<self.MIN_MOVE: return
        if not self.active: self.window.add_css_class("pointer")
        if self.source: GLib.source_remove(self.source); self.source=0
        ms=self.idle_ms()
        if ms: self.source=GLib.timeout_add(ms,self._idle)
    def _idle(self): self.source=0; self.off(); return GLib.SOURCE_REMOVE
    def off(self):
        if self.source: GLib.source_remove(self.source); self.source=0
        if self.active: self.window.remove_css_class("pointer")
