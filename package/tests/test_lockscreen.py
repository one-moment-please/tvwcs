"""TVWCS's lock screen: when it is used, and the locker command it runs (no display needed)."""
import unittest

from tvwcs import lockscreen, system_actions

def which_of(*names): return lambda n: f"/usr/bin/{n}" if n in names else None

class LockScreenTests(unittest.TestCase):
    def test_used_only_when_chosen_and_its_locker_is_installed(self):
        tv={"TVWCS_SESSION":"i3"}   # TV mode always locks with TVWCS's lock screen; a desktop session keeps its own locker
        self.assertEqual(lockscreen.command({},tv,which_of("i3lock"))[1:],["lock"])
        self.assertIsNone(lockscreen.command({},{},which_of("i3lock")))
        self.assertIsNone(lockscreen.command({},tv,which_of("xdg-screensaver")))
        self.assertIsNone(lockscreen.command({},{**tv,"SWAYSOCK":"/run/sway"},which_of("i3lock")))   # sway needs swaylock
    def test_screen_saver_while_locked_uses_xsecurelock_on_x_only(self):
        on={"screensaver_on_lock":True}
        self.assertTrue(lockscreen.saver_lock(on,{},which_of("xsecurelock")))
        self.assertEqual(lockscreen.command(on,{"TVWCS_SESSION":"i3"},which_of("xsecurelock"))[1:],["lock"])   # even without i3lock
        self.assertFalse(lockscreen.saver_lock(on,{},which_of("i3lock")))
        self.assertFalse(lockscreen.saver_lock(on,{"SWAYSOCK":"/run/sway"},which_of("xsecurelock")))
        self.assertFalse(lockscreen.saver_lock({},{},which_of("xsecurelock")))
        env=lockscreen.xsecurelock_env({},"/run/saver")
        self.assertEqual(env["XSECURELOCK_SAVER"],"/run/saver"); self.assertEqual(env["XSECURELOCK_AUTH_TIMEOUT"],"60")
        self.assertEqual(env["XSECURELOCK_BLANK_TIMEOUT"],"-1"); self.assertEqual(env["XSECURELOCK_SAVER_STOP_ON_BLANK"],"1")
    def test_the_power_menu_lock_uses_it(self):
        cmd=system_actions.command_for("lock",{},{"TVWCS_SESSION":"i3"},which_of("i3lock"))
        self.assertEqual(cmd[-1],"lock")
        self.assertEqual(system_actions.command_for("lock",{},{},which_of("i3lock")),["i3lock","-c","000000"])
    def test_locker_arguments(self):
        self.assertEqual(lockscreen.locker_argv("i3lock",[("","/run/lock.png")]),["i3lock","-e","-f","-c","1b1b1b","-i","/run/lock.png"])
        self.assertEqual(lockscreen.locker_argv("i3lock",[]),["i3lock","-e","-f","-c","1b1b1b"])
        self.assertEqual(lockscreen.locker_argv("i3lock",[],nofork=True),["i3lock","-e","-f","-c","1b1b1b","-n"])
        self.assertEqual(lockscreen.locker_argv("swaylock",[("HDMI-A-1","/a.png"),("DP-1","/b.png")]),
                         ["swaylock","-f","-e","-F","-c","1b1b1b","-i","HDMI-A-1:/a.png","-i","DP-1:/b.png"])
    def test_it_says_a_password_is_needed(self):
        self.assertIn("password",lockscreen.message("tv")); self.assertIn("tv",lockscreen.message("tv"))

if __name__=="__main__": unittest.main()
