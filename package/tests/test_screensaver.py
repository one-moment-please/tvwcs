import random, unittest
from tvwcs import screensaver as S

class ScreensaverTests(unittest.TestCase):
    def test_moves_without_bouncing_in_the_middle(self):
        self.assertEqual(S.step(100,100,2,2,50,20,1920,1080),(102,102,2,2,False))
    def test_bounces_off_the_right_and_bottom_edges(self):
        x,y,dx,dy,b=S.step(1869,1059,2,2,50,20,1920,1080)
        self.assertTrue(b); self.assertEqual((x,y),(1870,1060)); self.assertEqual((dx,dy),(-2,-2))
    def test_bounces_off_the_left_and_top_edges(self):
        x,y,dx,dy,b=S.step(1,1,-2,-2,50,20,1920,1080)
        self.assertTrue(b); self.assertEqual((x,y,dx,dy),(0,0,2,2))
    def test_stays_on_screen_for_a_long_time(self):
        x,y,dx,dy=10.0,10.0,2.2,2.2
        for _ in range(20000):
            x,y,dx,dy,_b=S.step(x,y,dx,dy,384,192,1920,1080)
            self.assertTrue(0<=x<=1920-384 and 0<=y<=1080-192)
    def test_next_colour_changes(self):
        rng=random.Random(1)
        for c in S.COLOURS: self.assertNotEqual(S.next_colour(c,rng),c)
    def test_logo_size(self):
        self.assertEqual(S.logo_size(1920,1080),(384,192))
        w,h=S.logo_size(1920,400,2.0); self.assertLessEqual(h,100); self.assertEqual(w,h*2)
    def test_start_says_what_is_missing_without_cairo(self):
        from unittest import mock
        with mock.patch.object(S,"running",return_value=None), mock.patch.object(S,"cairo_missing",return_value=True):
            self.assertIn("python3-gi-cairo",S.start("/nonexistent/tvwcs"))
    def test_screen_off(self):
        self.assertTrue(S.parse_monitor_off("DPMS (Energy Star):\n  Monitor is Off\n"))
        self.assertTrue(S.parse_monitor_off("  Monitor is in Standby\n"))
        self.assertFalse(S.parse_monitor_off("  Monitor is On\n")); self.assertFalse(S.parse_monitor_off(""))
        self.assertTrue(S.parse_sway_outputs_off('[{"active":true,"power":false},{"active":false,"power":true}]'))
        self.assertFalse(S.parse_sway_outputs_off('[{"active":true,"power":false},{"active":true,"power":true}]'))
        self.assertTrue(S.parse_sway_outputs_off('[{"active":true,"dpms":false}]'))   # sway before 1.8
        self.assertFalse(S.parse_sway_outputs_off("not json")); self.assertFalse(S.parse_sway_outputs_off("[]"))
    def test_saver_script_for_xsecurelock(self):
        import tempfile, os
        run=tempfile.mkdtemp(); path=S.saver_script("/opt/tvwcs/bin/tvwcs",{"XDG_RUNTIME_DIR":run})
        self.assertTrue(os.access(path,os.X_OK))
        with open(path) as f: self.assertIn("exec '/opt/tvwcs/bin/tvwcs' screensaver --xsecurelock",f.read())
    def test_the_tvwcs_logo_has_no_word_in_its_disc(self):
        self.assertIsNone(S.LOGO_WORDS["tvwcs"][1]); self.assertEqual(S.LOGO_WORDS["dvd"],("DVD","VIDEO"))

if __name__=="__main__": unittest.main()
