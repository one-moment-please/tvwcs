import unittest
from tvwcs.hotkeys import DEFAULT_HOTKEYS, HotkeyCapture, clean_hotkeys, describe, effective_binding, is_modifier_only, normalize_spec, render_i3, used_by, valid_spec, xcape_mapping

class HotkeyTests(unittest.TestCase):
    def test_validation(self):
        for ok in ("F2","Shift+F2","Mod4+space","Mod4","Mod4+Shift+Return"): self.assertTrue(valid_spec(ok),ok)
        for bad in ("","Mod4+Shift","F2+F3","Shift+Shift+a","Mod4+a b","a;rm"): self.assertFalse(valid_spec(bad),bad)
    def test_describe(self):
        self.assertEqual(describe("F2"),"F2"); self.assertEqual(describe("Shift+F2"),"Shift + F2")
        self.assertEqual(describe("Mod4"),"Super (tap)"); self.assertEqual(describe("Mod4+Shift+a"),"Super + Shift + A"); self.assertEqual(describe(""),"Not set")
    def test_normalize_orders_modifiers(self):
        self.assertEqual(normalize_spec(["Shift","Mod4","a"]),"Mod4+Shift+a")
    def test_defaults_tap_super_on_the_keyboard_and_f2_on_the_remote(self):
        hk=clean_hotkeys(None); self.assertEqual(hk,DEFAULT_HOTKEYS)
        self.assertTrue(is_modifier_only("Mod4")); self.assertEqual(effective_binding("menu","Mod4"),"F13")
        self.assertEqual(xcape_mapping(hk),"Super_L=F13")
        conf=render_i3(hk,"/opt/t v/tvwcs")
        self.assertIn("bindsym F13 exec --no-startup-id '/opt/t v/tvwcs' toggle",conf)
        self.assertIn("bindsym F2 exec --no-startup-id '/opt/t v/tvwcs' toggle",conf); self.assertIn("bindsym Shift+F2 exec",conf)
        self.assertEqual(conf.count("bindsym"),3)   # unset keyboard/gamepad keys bind nothing
        self.assertNotIn("bindsym Mod4 ",conf)   # binding Super itself would steal Super+Enter etc.
        for line in conf.splitlines():   # i3 has no end-of-line comments; one would become arguments to tvwcs
            if line.startswith("bindsym"): self.assertNotIn("#",line)
    def test_two_lone_modifiers_for_one_action_share_its_spare_key(self):
        hk=clean_hotkeys({"keyboard":{"menu":"Mod4","guide":"Mod1"},"gamepad":{"menu":"Control"}})
        self.assertEqual(xcape_mapping(hk),"Super_L=F13;Alt_L=F14;Control_L=F13")
        self.assertEqual(render_i3(hk,"t").count("bindsym F13 "),1)   # i3 rejects a key bound twice
    def test_used_by_finds_the_slot_holding_a_key(self):
        self.assertEqual(used_by(DEFAULT_HOTKEYS,"F2"),("remote","menu")); self.assertIsNone(used_by(DEFAULT_HOTKEYS,"F2",("remote","menu")))
        self.assertIsNone(used_by(DEFAULT_HOTKEYS,"F9"))
    def test_capture_plain_key_and_chord(self):
        c=HotkeyCapture(); self.assertEqual(c.press("F2",()),"F2")
        c=HotkeyCapture(); self.assertEqual(c.press("a",("Shift","Mod4")),"Mod4+Shift+a")
    def test_capture_lone_modifier_on_release(self):
        c=HotkeyCapture(); self.assertIsNone(c.press("Super_L",())); self.assertEqual(c.release("Super_L"),"Mod4")
    def test_modifier_used_in_a_chord_is_not_a_lone_modifier(self):
        c=HotkeyCapture(); c.press("Super_L",()); self.assertEqual(c.press("space",("Mod4",)),"Mod4+space"); self.assertIsNone(c.release("Super_L"))
if __name__=="__main__": unittest.main()
