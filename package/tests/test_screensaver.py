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
    def test_the_dvd_logo_is_gone(self):
        from tvwcs.model import SCREENSAVER_LOGOS, _clean_settings
        self.assertNotIn("dvd",SCREENSAVER_LOGOS)
        self.assertEqual(_clean_settings({"screensaver_logo":"dvd"})["screensaver_logo"],"tvwcs")   # chosen before 4.1
    def test_the_qr_code_has_a_finder_pattern_on_the_left(self):
        dark=S.qr_modules(40,9,6)
        ring={(6+c,1+r) for c in range(7) for r in range(7) if c in (0,6) or r in (0,6)}
        centre={(6+c,1+r) for c in range(2,5) for r in range(2,5)}
        light={(6+c,1+r) for c in range(-1,8) for r in range(-1,8)}-ring-centre
        self.assertTrue(ring<=dark and centre<=dark); self.assertFalse(light&dark)
        self.assertTrue(any(c>14 for c,_r in dark))   # random squares fill the rest
        self.assertEqual(dark,S.qr_modules(40,9,6))    # the same every time

    def test_on_sway_it_needs_gtk4_layer_shell_preloaded(self):
        import tempfile, os
        d=tempfile.mkdtemp()
        self.assertFalse(S.layer_shell_missing({"DISPLAY":":0"},dirs=(d,)))            # i3: a fullscreen window
        if not __import__("glob").glob(f"/usr/lib/*/girepository-1.0/{S.LAYER_SHELL_TYPELIB}"):
            self.assertTrue(S.layer_shell_missing({"SWAYSOCK":"/run/sway"},dirs=(d,)))
        d=os.path.join(tempfile.mkdtemp(),"girepository-1.0"); os.makedirs(d)
        open(os.path.join(d,S.LAYER_SHELL_TYPELIB),"w").close()
        if not __import__("glob").glob(f"/usr/lib/*/{S.LAYER_SHELL_LIB}"):   # the typelib alone is not enough
            self.assertTrue(S.layer_shell_missing({"SWAYSOCK":"/run/sway"},dirs=(d,)))
        open(os.path.join(os.path.dirname(d),S.LAYER_SHELL_LIB),"w").close()
        self.assertFalse(S.layer_shell_missing({"SWAYSOCK":"/run/sway"},dirs=(d,)))
        self.assertEqual(S.launch_env({"SWAYSOCK":"s","LD_PRELOAD":"libx.so"})["LD_PRELOAD"],"libgtk4-layer-shell.so.0 libx.so")
        self.assertEqual(S.launch_env({"SWAYSOCK":"s","LD_PRELOAD":"libgtk4-layer-shell.so.0"})["LD_PRELOAD"],"libgtk4-layer-shell.so.0")
        self.assertNotIn("LD_PRELOAD",S.launch_env({"DISPLAY":":0"}))

if __name__=="__main__": unittest.main()

class I3SpreadTests(unittest.TestCase):
    def test_focused_workspace_from_i3(self):
        from unittest import mock
        ws='[{"name":"1","focused":false},{"name":"3: web","focused":true}]'
        with mock.patch.object(S,"_i3_command",return_value=ws): self.assertEqual(S._i3_focused_workspace(),"3: web")
        with mock.patch.object(S,"_i3_command",return_value=""): self.assertIsNone(S._i3_focused_workspace())
        with mock.patch.object(S,"_i3_command",return_value="not json"): self.assertIsNone(S._i3_focused_workspace())
    def test_no_i3_commands_on_sway(self):
        from unittest import mock
        with mock.patch.dict(__import__("os").environ,{"SWAYSOCK":"/run/x"}), mock.patch("subprocess.run") as run:
            self.assertEqual(S._i3_command("workspace 1"),""); run.assert_not_called()
