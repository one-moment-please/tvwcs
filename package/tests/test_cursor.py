"""Hiding the mouse pointer (cursor.py): when, for how long, what runs, and where a resting pointer is moved."""
import unittest

from tvwcs import cursor

class CursorTests(unittest.TestCase):
    def test_only_in_tv_mode(self):
        tv={"TVWCS_SESSION":"i3"}; has=lambda n:"/usr/bin/"+n
        self.assertTrue(cursor.hide_enabled({},tv,has)); self.assertFalse(cursor.hide_enabled({},{},has))
        self.assertFalse(cursor.hide_enabled({},tv,lambda n:None))   # i3 without unclutter
        self.assertTrue(cursor.hide_enabled({},{**tv,"SWAYSOCK":"/s"},lambda n:None))   # sway hides it itself
        self.assertEqual(cursor.hide_seconds({}),3)
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
        h.apply({},{"TVWCS_SESSION":"i3"})
        self.assertEqual(ran[0][-2:],["-x","unclutter"]); self.assertEqual(started,[["unclutter","-idle","3"]])
        h.apply({},{"TVWCS_SESSION":"i3"}); self.assertEqual(len(started),1)   # unchanged: left running
        h.apply({},{}); self.assertEqual(started[-1],"stopped"); self.assertIsNone(h.proc)
    def test_hider_on_sway(self):
        ran=[]
        h=cursor.CursorHider(run=lambda argv,**k:ran.append(argv),popen=None,which=lambda n:None)
        h.apply({},{"SWAYSOCK":"/run/sway","TVWCS_SESSION":"sway"})
        self.assertEqual(ran,[["swaymsg","seat * hide_cursor 3000"]])
    def test_parker_moves_a_resting_pointer_once(self):
        p=cursor.Parker()
        self.assertFalse(p.tick((10,10),0.5,1)); self.assertFalse(p.tick((10,10),0.5,1)); self.assertTrue(p.tick((10,10),0.5,1))
        p.moved_to((1918,1078))
        for _ in range(4): self.assertFalse(p.tick((1918,1078),0.5,1))   # stays put once moved
        self.assertFalse(p.tick((50,50),0.5,1)); self.assertFalse(p.tick((50,50),0.5,1)); self.assertTrue(p.tick((50,50),0.5,1))
        self.assertEqual(cursor.corner({"x":0,"y":0,"width":1920,"height":1080}),(1918,1078))

if __name__=="__main__": unittest.main()
