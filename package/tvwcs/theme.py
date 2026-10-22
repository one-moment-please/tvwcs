"""The Metro / Modern UI theme. Flat, square, high-contrast; every corner radius is 0."""
from __future__ import annotations
import re
from tvwcs.widgets import METRO_COLORS
from tvwcs.model import WALLPAPERS

CSS="""
window.tvwcs-window, .tvwcs-root { background: @BG@; color: @FG@; font-family: "Segoe UI", "Selawik", "Open Sans", "Noto Sans", "Cantarell", sans-serif; border-radius: 0; box-shadow: none; }
.pane { background: @PANE@; }
.brand { font-size: 26px; font-weight: 300; letter-spacing: 2px; }
.pane-title { font-size: 34px; font-weight: 200; }
.muted { color: @MUTED@; font-size: 14px; }
.section-title { font-size: 13px; font-weight: 700; letter-spacing: 2px; color: @ACCENT@; margin-top: 12px; margin-bottom: 2px; }
.channel-number { font-weight: 700; color: @ACCENT@; }
.favorite-mark { color: @MUTED@; font-size: 18px; }
button:focus .favorite-mark { color: #ffffff; }
/* a Quick Menu row that is open now: a thin band down its left side (white while selected) */
button.launch-row.open-app { box-shadow: inset 3px 0 @ACCENT@; }
button.launch-row.open-app:focus, button.launch-row.open-app:focus-visible { box-shadow: inset 6px 0 #ffffff; }
button.launch-row.open-app:dir(rtl) { box-shadow: inset -3px 0 @ACCENT@; }   /* mirrored: down its right side */
button.launch-row.open-app:dir(rtl):focus, button.launch-row.open-app:dir(rtl):focus-visible { box-shadow: inset -6px 0 #ffffff; }
.child-marker { color: @FAINT@; font-size: 22px; }
button { min-height: 44px; min-width: 44px; padding: 0 14px; border: none; border-radius: 0; background: @RAISED@; background-image: none; color: @FG@; box-shadow: none; text-shadow: none; font-size: 15px; }
window.pointer button:hover { background: @HOVER@; }
button:focus, button:focus-visible, button:active { background: @ACCENT@; color: #ffffff; outline: 3px solid #ffffff; outline-offset: -3px; }
button:focus .channel-number, button:focus .muted, button:focus .child-marker { color: #ffffff; }
button:focus label { font-weight: 700; }
button.active { box-shadow: inset 0 -4px @ACCENT@; }   /* on, or the main choice: a bar, so it never looks selected */
button.active:focus, button.active:focus-visible { box-shadow: none; }
button.dialog-button { padding: 0 16px; }
button.danger:focus, button.danger:focus-visible { background: #e81123; }
button.square { min-width: 44px; min-height: 44px; padding: 0; }
button.close-button { background: #c50f1f; color: #ffffff; }
window.pointer button.close-button:hover { background: #e81123; }
button.close-button:focus, button.close-button:focus-visible, button.close-button:active { background: #e81123; outline: 3px solid #ffffff; outline-offset: -3px; }
.mode-button { min-width: 44px; padding: 0; }
button.options-toggle { min-width: 22px; padding: 0; }   /* ⋯ is half as wide as it is tall: ← or a right-click opens the same menu */
button.category-header { background: @HEADER@; font-size: 18px; font-weight: 300; margin-top: 6px; }
window.pointer button.category-header:hover { background: @HOVER@; }
button.category-header:focus, button.category-header:focus-visible { background: @ACCENT@; outline: 3px solid #ffffff; outline-offset: -3px; }
.description { color: @MUTED@; font-size: 13px; }
button:focus .description, .tvwcs-selected .description { color: #e3eefa; }
.pin-display { font-size: 34px; font-weight: 300; letter-spacing: 4px; }
button.pin-key { font-size: 24px; min-height: 64px; }
button.pin-key.kb-key { font-size: 18px; min-height: 46px; min-width: 0; padding: 0 2px; }
.text-display { font-size: 22px; min-height: 48px; }
.field-value { color: @MUTED@; font-size: 14px; }
button.field-row { padding-top: 6px; padding-bottom: 6px; }
button.field-row:focus .field-value { color: inherit; }
.setting-value { color: @ACCENT@; font-weight: 700; }
button:focus .setting-value { color: #ffffff; }
.tvwcs-selected { background: @ACCENT@; color: #ffffff; outline: 3px solid #ffffff; outline-offset: -3px; }
.tvwcs-selected label { font-weight: 700; color: #ffffff; }
entry, entry.search, entry.password { min-height: 46px; padding: 0 10px; border: 2px solid @BORDER@; border-radius: 0; background: @RAISED@; background-image: none; color: @FG@; box-shadow: none; font-size: 17px; }
entry:focus-within { background: #ffffff; color: #000000; border-color: @ACCENT@; }
entry:focus-within text, entry:focus-within image { color: #000000; }
.icon-tile { color: #ffffff; font-weight: 700; font-size: 15px; }
.badge { background: #e81123; color: #ffffff; font-size: 10px; font-weight: 700; min-width: 16px; min-height: 16px; padding: 0 3px; border-radius: 0; }
.modal-scrim { background: @SCRIM@; }
.modal-card { background: @CARD@; padding: 22px; border: 2px solid @ACCENT@; border-radius: 0; }
.error { color: @ERROR@; }
popover > contents, popover contents { background: @CARD@; color: @FG@; border: 2px solid @ACCENT@; border-radius: 0; box-shadow: none; padding: 6px; }
scrollbar slider { background: #6e6e6e; border-radius: 0; min-width: 8px; min-height: 8px; }
scrollbar trough { background: transparent; border-radius: 0; }
separator { background: @LINE@; min-height: 1px; }
checkbutton check { border-radius: 0; background: @RAISED@; border: 2px solid @BORDER@; box-shadow: none; background-image: none; -gtk-icon-source: none; min-width: 22px; min-height: 22px; }
checkbutton check:checked { background: @ACCENT@; border-color: @ACCENT@; -gtk-icon-source: -gtk-icontheme("object-select-symbolic"); color: #ffffff; }
dropdown > button, dropdown button { border-radius: 0; }
.quick-status { background: @STATUS@; padding: 6px 14px 8px 14px; }
button.clock-button, button.status-icon { background: transparent; }
button.clock-button { padding: 4px 8px; }
window.pointer button.clock-button:hover, window.pointer button.status-icon:hover { background: @RAISED@; }
button.clock-button:focus, button.clock-button:focus-visible, button.status-icon:focus, button.status-icon:focus-visible { background: @ACCENT@; outline: 3px solid #ffffff; outline-offset: -3px; }
.clock-time { font-size: 22px; font-weight: 300; }
.clock-date { color: @MUTED@; font-size: 15px; }
button:focus .clock-date { color: #ffffff; }
button.status-wide { padding: 0 8px; }
.status-count { font-size: 14px; font-weight: 700; }
button.status-off { color: @FAINT@; }
/* the Quick Menu's channel hint and the "Starting …" card */
.channel-hint { color: @MUTED@; font-size: 15px; }
entry.channel-entry { font-size: 24px; }
entry.channel-entry text { letter-spacing: 2px; }
entry.tv-search { border-color: @RAISED@; }
entry.tv-search > image { -gtk-icon-size: 0; min-width: 0; margin: 0; padding: 0; opacity: 0; }
entry.tv-search text placeholder { color: @ACCENT@; opacity: 1; }
.digit-box { min-width: 56px; min-height: 64px; font-size: 34px; font-weight: 300; background: @RAISED@; border: 2px solid @BORDER@; }
.digit-box.current { border-color: @ACCENT@; }
button.menu-item { padding: 0 16px; }
/* a Quick Menu row's options, unfolded above it, and a status icon's panel */
.row-options button.menu-item { min-height: 40px; }
.row-options button.menu-item:not(:focus):not(:active) { background: @HEADER@; }
.status-panel { background: @HEADER@; padding: 10px 12px; }
.panel-title { font-size: 15px; font-weight: 700; margin-top: 2px; }
.status-panel button { min-height: 40px; }
.status-panel scale { padding: 0 6px; }
.status-panel scale trough { background: @TROUGH@; border: none; border-radius: 0; min-height: 8px; }
.status-panel scale highlight { background: @ACCENT@; border: none; border-radius: 0; min-height: 8px; margin: 0; }
.status-panel scale slider { background: @FG@; border: none; border-radius: 0; min-width: 12px; min-height: 20px; margin: -6px 0; box-shadow: none; }
"""

# The two looks (Settings > Appearance > Theme). The selection stays a solid accent block with white text in both.
PALETTES={
    "dark":{"BG":"#000000","FG":"#ffffff","PANE":"#1b1b1b","RAISED":"#2d2d2d","HOVER":"#3f3f3f","HEADER":"#262626","CARD":"#262626",
            "STATUS":"#141414","MUTED":"#b5b5b5","FAINT":"#7d7d7d","BORDER":"#5a5a5a","LINE":"#333333","SCRIM":"rgba(0, 0, 0, 0.78)",
            "ERROR":"#ff5a67","ON":"#6ccb5f","TROUGH":"#3a3a3a"},
    "light":{"BG":"#d6d6d6","FG":"#000000","PANE":"#f2f2f2","RAISED":"#e1e1e1","HOVER":"#cdcdcd","HEADER":"#e8e8e8","CARD":"#fafafa",
             "STATUS":"#e4e4e4","MUTED":"#4a4a4a","FAINT":"#767676","BORDER":"#8a8a8a","LINE":"#c8c8c8","SCRIM":"rgba(255, 255, 255, 0.72)",
             "ERROR":"#c50f1f","ON":"#107c10","TROUGH":"#c4c4c4"},
}

def render_css(accent, scale=1.0, extra="", theme="dark"):
    """The theme (plus `extra` rules, such as the Settings app's) with the accent colour and the look's colours filled in
    and every pixel measure multiplied by `scale`. Hover colours apply only while the mouse is in use (the window has
    the "pointer" class, see widgets.PointerWatch): a pointer hidden after a few seconds would otherwise keep marking
    whatever happens to be under it, next to the remote's real selection."""
    css=(CSS+extra).replace("@ACCENT@",accent)
    for key,value in PALETTES.get(theme,PALETTES["dark"]).items(): css=css.replace(f"@{key}@",value)
    if scale!=1.0:
        css=re.sub(r"(?<![\w.#-])(\d+)px",lambda m:f"{0 if m.group(1)=='0' else max(1,round(int(m.group(1))*scale))}px",css)
    tiles="\n".join(f".tile-{i} {{ background: {c}; }}" for i,c in enumerate(METRO_COLORS))
    walls="\n".join(f".wall-{i}, button.wall-{i}:focus, button.wall-{i}:hover {{ background: {c}; }}" for i,c in enumerate(WALLPAPERS))
    return css+"\n"+tiles+"\n"+walls
