"""Small GTK helpers shared by the TVWCS windows: scaling, icons, navigation groups."""
from __future__ import annotations
import os
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, Gtk

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

def usable(w): return w.get_visible() and w.get_mapped() and w.get_sensitive()

class NavGroup(list):
    """Controls on one row, reached with Left/Right. Up/Down lands on `entry` (the row's main control).
    Rows whose options fold away have `toggle` (the options button) plus `expand` and `expanded`."""
    def __init__(self,widgets=(),entry=None):
        super().__init__(widgets); self.entry=entry; self.toggle=None; self.expand=None; self.expanded=None; self.column=False   # column: a grid row, Up/Down keeps the column
        self.lane=None   # in a multi-column layout (Settings), which column the row is in; ←/→ jump between lanes

def screen_height():
    """The tallest connected monitor's height in logical pixels (0 when there is no display yet)."""
    display=Gdk.Display.get_default()
    if display is None: return 0
    monitors=display.get_monitors(); best=0
    for i in range(monitors.get_n_items()):
        best=max(best,monitors.get_item(i).get_geometry().height)
    return best
