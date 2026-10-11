"""The Metro / Modern UI theme. Flat, square, high-contrast; every corner radius is 0."""
from __future__ import annotations
import re
from widgets import METRO_COLORS

CSS="""
window.tvwcs-window, .tvwcs-root { background: #000000; color: #ffffff; font-family: "Segoe UI", "Selawik", "Open Sans", "Noto Sans", "Cantarell", sans-serif; border-radius: 0; box-shadow: none; }
.pane { background: #1b1b1b; }
.brand { font-size: 26px; font-weight: 300; letter-spacing: 2px; }
.pane-title { font-size: 34px; font-weight: 200; }
.muted { color: #9a9a9a; font-size: 13px; }
.section-title { font-size: 13px; font-weight: 700; letter-spacing: 2px; color: @ACCENT@; margin-top: 12px; margin-bottom: 2px; }
.channel-number { font-weight: 700; color: @ACCENT@; }
.child-marker { color: #7d7d7d; font-size: 22px; }
button { min-height: 44px; min-width: 44px; padding: 0 14px; border: none; border-radius: 0; background: #2d2d2d; background-image: none; color: #ffffff; box-shadow: none; text-shadow: none; font-size: 15px; }
button:hover { background: #3f3f3f; }
button:focus, button:focus-visible, button:active { background: @ACCENT@; color: #ffffff; outline: 3px solid #ffffff; outline-offset: -3px; }
button:focus .channel-number, button:focus .muted, button:focus .child-marker { color: #ffffff; }
button:focus label { font-weight: 700; }
button.active { background: @ACCENT@; }
button.launch-row { text-align: left; }
button.dialog-button { padding: 0 16px; }
button.danger:focus, button.danger:focus-visible { background: #e81123; }
.window-controls button { min-width: 52px; }
.window-controls button.close-button:hover, .window-controls button.close-button:focus { background: #e81123; }
.mode-button, button.options-toggle { min-width: 44px; padding: 0; }
button.category-header { background: #262626; font-size: 18px; font-weight: 300; margin-top: 6px; }
button.category-header:hover { background: #343434; }
button.category-header:focus, button.category-header:focus-visible { background: @ACCENT@; outline: 3px solid #ffffff; outline-offset: -3px; }
.description { color: #8a8a8a; font-size: 12px; }
button:focus .description, .tvwcs-selected .description { color: #e3eefa; }
.pin-display { font-size: 34px; font-weight: 300; letter-spacing: 4px; }
button.pin-key { font-size: 24px; min-height: 64px; }
.setting-value { color: @ACCENT@; font-weight: 700; }
button:focus .setting-value { color: #ffffff; }
.tvwcs-selected { background: @ACCENT@; color: #ffffff; outline: 3px solid #ffffff; outline-offset: -3px; }
.tvwcs-selected label { font-weight: 700; color: #ffffff; }
entry, entry.search, entry.password { min-height: 46px; padding: 0 10px; border: 2px solid #5a5a5a; border-radius: 0; background: #2d2d2d; background-image: none; color: #ffffff; box-shadow: none; font-size: 17px; }
entry:focus-within { background: #ffffff; color: #000000; border-color: @ACCENT@; }
entry:focus-within text, entry:focus-within image { color: #000000; }
.icon-tile { color: #ffffff; font-weight: 700; font-size: 15px; }
.badge { background: #e81123; color: #ffffff; font-size: 10px; font-weight: 700; min-width: 16px; min-height: 16px; padding: 0 3px; border-radius: 0; }
.modal-scrim { background: rgba(0, 0, 0, 0.78); }
.modal-card { background: #262626; padding: 22px; border: 2px solid @ACCENT@; border-radius: 0; }
.error { color: #ff5a67; }
popover > contents, popover contents { background: #2b2b2b; border: 2px solid @ACCENT@; border-radius: 0; box-shadow: none; padding: 6px; }
scrollbar slider { background: #6e6e6e; border-radius: 0; min-width: 8px; min-height: 8px; }
scrollbar trough { background: transparent; border-radius: 0; }
separator { background: #333333; min-height: 1px; }
checkbutton check { border-radius: 0; background: #2d2d2d; border: 2px solid #7a7a7a; box-shadow: none; background-image: none; -gtk-icon-source: none; min-width: 22px; min-height: 22px; }
checkbutton check:checked { background: @ACCENT@; border-color: @ACCENT@; -gtk-icon-source: -gtk-icontheme("object-select-symbolic"); color: #ffffff; }
dropdown > button, dropdown button { border-radius: 0; }
"""

def render_css(accent, scale=1.0):
    """The theme with the accent colour filled in and every pixel measure multiplied by `scale`."""
    css=CSS.replace("@ACCENT@",accent)
    if scale!=1.0:
        css=re.sub(r"(?<![\w.#-])(\d+)px",lambda m:f"{0 if m.group(1)=='0' else max(1,round(int(m.group(1))*scale))}px",css)
    tiles="\n".join(f".tile-{i} {{ background: {c}; }}" for i,c in enumerate(METRO_COLORS))
    return css+"\n"+tiles
