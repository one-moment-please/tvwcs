"""TVWCS's lock screen: when it is used, and the swaylock command it runs (no display needed)."""
import unittest

from tvwcs import lockscreen, system_actions

def which_of(*names): return lambda n: f"/usr/bin/{n}" if n in names else None

class LockScreenTests(unittest.TestCase):
    def test_used_in_tv_mode_when_swaylock_is_installed(self):
        tv={"TVWCS_SESSION":"sway"}   # TV mode always locks with TVWCS's lock screen; a desktop session keeps its own locker
        self.assertEqual(lockscreen.command({},tv,which_of("swaylock"))[1:],["lock"])
        self.assertIsNone(lockscreen.command({},{},which_of("swaylock")))
        self.assertIsNone(lockscreen.command({},tv,which_of("loginctl")))
    def test_the_power_menu_lock_uses_it(self):
        self.assertEqual(system_actions.command_for("lock",{},{"TVWCS_SESSION":"sway"},which_of("swaylock"))[-1],"lock")
        self.assertEqual(system_actions.command_for("lock",{},{},which_of("swaylock")),["swaylock","-f","-c","000000"])
        self.assertEqual(system_actions.command_for("lock",{},{},which_of("loginctl")),["loginctl","lock-session"])
        self.assertIsNone(system_actions.command_for("lock",{},{},which_of()))
    def test_locker_arguments_use_the_accent_colour(self):
        argv=lockscreen.locker_argv("#107C10")
        self.assertEqual(argv[:6],["swaylock","-f","-e","-F","-c","1b1b1b"]); self.assertEqual(argv[argv.index("--ring-color")+1],"107c10")
        self.assertEqual(lockscreen.locker_argv("nonsense")[lockscreen.locker_argv().index("--ring-color")+1],"0078d7")

if __name__=="__main__": unittest.main()
