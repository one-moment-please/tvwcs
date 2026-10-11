"""Remote-navigation logic of the main window, exercised without GTK: `gi` is replaced by a stub and the
window's methods run against fake widgets. (Appearance and real focus behaviour still need a real desktop.)"""
import sys, types, unittest
from unittest.mock import MagicMock

_SAVED={k:sys.modules.get(k) for k in ("gi","gi.repository")}
class _Stub(types.ModuleType):
    def __getattr__(self,name):
        if name.startswith("__"): raise AttributeError(name)
        value=MagicMock(); setattr(self,name,value); return value
def _install_stub():
    gi=types.ModuleType("gi"); gi.require_version=lambda *a,**k:None
    repo=types.ModuleType("gi.repository")
    Gdk=_Stub("Gdk")
    class ModifierType: CONTROL_MASK=4; ALT_MASK=8; SUPER_MASK=16; META_MASK=32; SHIFT_MASK=1
    Gdk.ModifierType=ModifierType
    for n,v in dict(KEY_Escape=1,KEY_Down=2,KEY_Up=3,KEY_Left=4,KEY_Right=5,KEY_Return=6,KEY_KP_Enter=7,KEY_Back=8,KEY_BackSpace=9).items(): setattr(Gdk,n,v)
    Gdk.keyval_to_unicode=lambda k:k if k>=32 else 0
    Gtk=_Stub("Gtk")
    class Editable: pass
    Gtk.Editable=Editable; Gtk.ApplicationWindow=type("ApplicationWindow",(),{}); Gtk.Application=type("Application",(),{}); Gtk.Window=type("Window",(),{})
    repo.Gdk=Gdk; repo.Gtk=Gtk; repo.Gio=_Stub("Gio"); repo.GLib=_Stub("GLib")
    sys.modules["gi"]=gi; sys.modules["gi.repository"]=repo; gi.repository=repo
_install_stub()
import importlib
for m in ("widgets","theme","ui_settings","ui_window"): sys.modules.pop(m,None)
ui_window=importlib.import_module("ui_window")
for k,v in _SAVED.items():
    if v is None: sys.modules.pop(k,None)
    else: sys.modules[k]=v

from widgets import NavGroup
Editable=ui_window.Gtk.Editable

class W:
    focus=None
    def __init__(self,name,parent=None): self.name=name; self.parent=parent; self.focused=0
    def get_visible(self): return True
    def get_mapped(self): return True
    def get_sensitive(self): return True
    def is_ancestor(self,other):
        p=self.parent
        while p is not None:
            if p is other: return True
            p=p.parent
        return False
    def grab_focus(self): W.focus=self; self.focused+=1; return True
class Entry(W,Editable): pass

def make_window(**state):
    win=ui_window.TVWCSWindow.__new__(ui_window.TVWCSWindow)
    win.app=MagicMock(); win._groups={"quick":[],"guide":[],"options":[]}; win._header_group=[]; win._result_groups=[]; win._modal_groups=[]
    win.guide_open=False; win.options_open=False; win.guide_pane=None; win.options_pane=None; win._last_focus={}
    win._search_results=[]; win._selected_result=0; win._capture=None; win._pin=None
    win.search_entry=Entry("search"); win.get_focus=lambda:W.focus
    win._type_to_search=MagicMock(); win._escape=MagicMock()
    for k,v in state.items(): setattr(win,k,v)
    return win

def options_row(win,expanded=False,pane="quick",results=False):
    toggle,opt,main=W("toggle"),W("opt"),W("main")
    state={"open":expanded}
    g=NavGroup([toggle,opt,main],entry=main); g.toggle=toggle
    g.expanded=lambda:state["open"]; g.expand=MagicMock(side_effect=lambda:state.update(open=True))
    (win._result_groups if results else win._groups[pane]).append(g)
    if not expanded: opt.get_mapped=lambda:False      # collapsed options are not on screen
    return g,toggle,opt,main

class NavigationTests(unittest.TestCase):
    def test_exact_match_beats_container_match(self):
        # A category header whose rows sit inside it: focus on a row must not be read as focus on the header.
        win=make_window(); container=W("container"); row=W("row",parent=container)
        groups=[NavGroup([container]),NavGroup([row])]
        self.assertEqual(win._group_index(groups,row),1); self.assertEqual(win._group_index(groups,container),0)
        self.assertEqual(win._group_index(groups,W("elsewhere",parent=container)),0)   # inside-match still works as a fallback
    def test_left_on_collapsed_options_button_expands_it(self):
        win=make_window(); g,toggle,opt,main=options_row(win); W.focus=toggle
        self.assertTrue(win._move_within_group(-1)); g.expand.assert_called_once()
    def test_left_again_when_expanded_stays_put(self):
        win=make_window(); g,toggle,opt,main=options_row(win,expanded=True); W.focus=toggle
        win._move_within_group(-1); g.expand.assert_not_called(); self.assertIs(W.focus,toggle)
    def test_left_on_expanded_search_result_options_returns_to_typing(self):
        win=make_window(); g,toggle,opt,main=options_row(win,expanded=True,results=True); W.focus=toggle
        win._move_within_group(-1); self.assertIs(W.focus,win.search_entry)
    def test_right_moves_through_the_row(self):
        win=make_window(); g,toggle,opt,main=options_row(win,expanded=True); W.focus=toggle
        win._move_within_group(1); self.assertIs(W.focus,opt); win._move_within_group(1); self.assertIs(W.focus,main)
    def test_right_past_the_end_of_the_quick_menu_opens_the_guide(self):
        win=make_window(); g,toggle,opt,main=options_row(win,expanded=True); W.focus=main
        win._move_within_group(1); win.app.show_panels.assert_called_once_with(True,False,focus="guide")
    def test_right_goes_into_an_already_open_guide(self):
        guide=W("guide_pane"); win=make_window(guide_open=True,guide_pane=guide); g,toggle,opt,main=options_row(win,expanded=True)
        inner=W("g1",parent=guide); win._groups["guide"].append(NavGroup([inner])); W.focus=main
        win._move_within_group(1); win.app.show_panels.assert_not_called(); self.assertIs(W.focus,inner)
    def test_right_past_the_end_of_the_guide_opens_settings(self):
        guide=W("guide_pane"); win=make_window(guide_open=True,guide_pane=guide)
        last=W("star",parent=guide); win._groups["guide"].append(NavGroup([W("main",parent=guide),last])); W.focus=last
        win._move_within_group(1); win.app.show_panels.assert_called_once_with(True,True,focus="options")
    def test_left_from_settings_closes_it_and_returns_to_the_guide(self):
        guide,options=W("guide"),W("options"); win=make_window(guide_open=True,options_open=True,guide_pane=guide,options_pane=options)
        row=W("row",parent=options); win._groups["options"].append(NavGroup([row])); W.focus=row
        win._move_within_group(-1); win.app.show_panels.assert_called_once_with(True,False,focus="guide")
    def test_right_in_settings_goes_nowhere(self):
        guide,options=W("guide"),W("options"); win=make_window(guide_open=True,options_open=True,guide_pane=guide,options_pane=options)
        row=W("row",parent=options); win._groups["options"].append(NavGroup([row])); W.focus=row
        win._move_within_group(1); win.app.show_panels.assert_not_called()
    def test_up_down_lands_on_the_main_button(self):
        win=make_window(); a=options_row(win,expanded=True); b=options_row(win,expanded=True); W.focus=a[3]
        win._move_group(1); self.assertIs(W.focus,b[3])

class TypingTests(unittest.TestCase):
    def press(self,win,key,state=0): return win._key_pressed(None,key,0,state)
    def test_typing_anywhere_goes_to_search(self):
        win=make_window(); W.focus=W("button")
        self.assertTrue(self.press(win,ord("f"))); win._type_to_search.assert_called_once_with("f")
    def test_space_and_control_keys_are_left_alone(self):
        win=make_window(); W.focus=W("button")
        self.assertFalse(self.press(win,ord(" "))); self.assertFalse(self.press(win,ord("c"),ui_window.Gdk.ModifierType.CONTROL_MASK))
        win._type_to_search.assert_not_called()
    def test_typing_in_a_text_field_is_not_hijacked(self):
        win=make_window(); W.focus=Entry("password"); self.press(win,ord("x")); win._type_to_search.assert_not_called()
    def test_typing_during_a_dialog_is_not_hijacked(self):
        win=make_window(); win._modal_groups=[NavGroup([W("ok")])]; W.focus=W("ok"); self.press(win,ord("x")); win._type_to_search.assert_not_called()
    def test_escape_is_handled_first(self):
        win=make_window(); W.focus=W("b"); self.assertTrue(self.press(win,1)); win._escape.assert_called_once()
    def test_back_key_does_the_same_as_escape(self):
        win=make_window(); W.focus=W("b"); self.assertTrue(self.press(win,ui_window.Gdk.KEY_Back)); win._escape.assert_called_once()
    def test_back_key_cancels_hotkey_capture(self):
        win=make_window(); win._capture=MagicMock(); win._end_capture=MagicMock(); win.get_focus=lambda:W.focus
        self.assertTrue(self.press(win,ui_window.Gdk.KEY_Back)); win._end_capture.assert_called_once_with(None)

class PinPadTests(unittest.TestCase):
    def pad(self,pin="1234"):
        from pinlock import PinGate, make_hash
        from model import LaunchProfile
        win=make_window(); profile=LaunchProfile("p","a.desktop","Kids",pin_hash=make_hash(pin))
        win.app.pin_gate=PinGate(); win._pin={"profile":profile,"on_ok":MagicMock(),"digits":"","shown":MagicMock()}
        win.close_modal=MagicMock(); win.ask_pin=MagicMock(); return win
    def test_digits_build_up_and_are_capped_at_eight(self):
        win=self.pad()
        for d in "123456789": win._pin_press(d)
        self.assertEqual(win._pin["digits"],"12345678"); win._pin_back(); self.assertEqual(win._pin["digits"],"1234567")
    def test_keyboard_digits_and_backspace_work_on_the_keypad(self):
        win=self.pad(); W.focus=W("button")
        for ch in "12": self.assertTrue(win._key_pressed(None,ord(ch),0,0))
        self.assertEqual(win._pin["digits"],"12"); win._key_pressed(None,ui_window.Gdk.KEY_BackSpace,0,0); self.assertEqual(win._pin["digits"],"1")
    def test_typing_on_the_keypad_does_not_start_a_search(self):
        win=self.pad(); win._modal_groups=[NavGroup([W("key")])]; W.focus=W("button")   # ask_pin always has the modal groups set
        win._key_pressed(None,ord("x"),0,0); win._type_to_search.assert_not_called()
    def test_right_pin_runs_the_action(self):
        win=self.pad(); on_ok=win._pin["on_ok"]; win._pin["digits"]="1234"; win._pin_submit()
        win.close_modal.assert_called_once(); on_ok.assert_called_once(); win.ask_pin.assert_not_called()
    def test_wrong_pin_asks_again_with_a_message(self):
        win=self.pad(); win._pin["digits"]="9999"; win._pin_submit()
        win.ask_pin.assert_called_once(); self.assertEqual(win.ask_pin.call_args[0][2],"Wrong PIN."); win._pin["on_ok"].assert_not_called()
    def test_too_many_wrong_pins_lock_the_keypad(self):
        win=self.pad()
        for _ in range(5): win._pin["digits"]="9999"; win._pin_submit()
        self.assertIn("Too many wrong tries",win.ask_pin.call_args[0][2])
    def test_up_down_keeps_the_keypad_column(self):
        win=self.pad(); rows=[]
        for r in range(3):
            g=NavGroup([W(f"r{r}c{c}") for c in range(3)]); g.column=True; rows.append(g)
        win._modal_groups=rows; W.focus=rows[0][2]
        win._move_group(1); self.assertIs(W.focus,rows[1][2]); win._move_group(1); self.assertIs(W.focus,rows[2][2]); win._move_group(-1); self.assertIs(W.focus,rows[1][2])

if __name__=="__main__": unittest.main()
