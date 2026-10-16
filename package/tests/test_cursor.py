"""Hiding the mouse pointer (cursor.py): when, for how long, what runs, and where a resting pointer is moved."""
import unittest

from tvwcs import cursor
from tvwcs.model import DEFAULT_SETTINGS, _clean_settings, apply_use

class CursorTests(unittest.TestCase):
    def test_default_follows_the_use(self):
        self.assertTrue(cursor.hide_enabled({"use":"tv","cursor_hide":None}))
        self.assertFalse(cursor.hide_enabled({"use":"desktop","cursor_hide":None}))
        self.assertTrue(cursor.hide_enabled({"use":"desktop","cursor_hide":True}))
        self.assertFalse(cursor.hide_enabled({"use":"tv","cursor_hide":False}))
        self.assertEqual(cursor.hide_ms({"use":"tv","cursor_hide":None,"cursor_hide_seconds":3}),3000)
        self.assertIsNone(cursor.hide_ms({"use":"desktop","cursor_hide":None}))
    def test_seconds_are_kept_in_range(self):
        self.assertEqual(cursor.hide_seconds({"cursor_hide_seconds":0}),3); self.assertEqual(cursor.hide_seconds({"cursor_hide_seconds":True}),3)
        self.assertEqual(cursor.clamp_seconds(0),1); self.assertEqual(cursor.clamp_seconds(99),60)
    def test_options_are_cleaned_and_reset_by_the_use(self):
        s=_clean_settings({"cursor_hide":"yes","cursor_hide_seconds":500})
        self.assertIsNone(s["cursor_hide"]); self.assertEqual(s["cursor_hide_seconds"],3)
        s=_clean_settings({"cursor_hide":False,"cursor_hide_seconds":10}); self.assertEqual((s["cursor_hide"],s["cursor_hide_seconds"]),(False,10))
        apply_use(s,"tv"); self.assertIsNone(s["cursor_hide"])
        self.assertIsNone(DEFAULT_SETTINGS["cursor_hide"])
    def test_sway_and_unclutter_commands(self):
        self.assertEqual(cursor.sway_command(True,3),"seat * hide_cursor 3000"); self.assertEqual(cursor.sway_command(False,3),"seat * hide_cursor 0")
        self.assertEqual(cursor.unclutter_argv(5),["unclutter","-idle","5"])
    def test_hider_on_x_replaces_unclutter(self):
        ran=[]; started=[]
        class Proc:
            def poll(self): return None
            def terminate(self): started.append("stopped")
            def wait(self,timeout=None): return 0
        h=cursor.CursorHider(run=lambda argv,**k:ran.append(argv),popen=lambda argv,**k:(started.append(argv),Proc())[1],which=lambda n:"/usr/bin/"+n)
        h.apply({"use":"tv","cursor_hide":None,"cursor_hide_seconds":3},{})
        self.assertEqual(ran[0][-2:],["-x","unclutter"]); self.assertEqual(started,[["unclutter","-idle","3"]])
        h.apply({"use":"tv","cursor_hide":None,"cursor_hide_seconds":3},{}); self.assertEqual(len(started),1)   # unchanged: left running
        h.apply({"use":"desktop","cursor_hide":None},{}); self.assertEqual(started[-1],"stopped"); self.assertIsNone(h.proc)
    def test_hider_on_sway(self):
        ran=[]
        h=cursor.CursorHider(run=lambda argv,**k:ran.append(argv),popen=None,which=lambda n:None)
        h.apply({"use":"tv","cursor_hide":None,"cursor_hide_seconds":5},{"SWAYSOCK":"/run/sway"})
        self.assertEqual(ran,[["swaymsg","seat * hide_cursor 5000"]])
    def test_parker_moves_a_resting_pointer_once(self):
        p=cursor.Parker()
        self.assertFalse(p.tick((10,10),0.5,1)); self.assertFalse(p.tick((10,10),0.5,1)); self.assertTrue(p.tick((10,10),0.5,1))
        p.moved_to((1918,1078))
        for _ in range(4): self.assertFalse(p.tick((1918,1078),0.5,1))   # stays put once moved
        self.assertFalse(p.tick((50,50),0.5,1)); self.assertFalse(p.tick((50,50),0.5,1)); self.assertTrue(p.tick((50,50),0.5,1))
        self.assertEqual(cursor.corner({"x":0,"y":0,"width":1920,"height":1080}),(1918,1078))

if __name__=="__main__": unittest.main()
