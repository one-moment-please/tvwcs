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
    def test_lock_at_start_only_when_on_in_tv_mode_with_a_password(self):
        tv={"TVWCS_SESSION":"sway"}; on={"lock_at_start":True}; sw=which_of("swaylock")
        self.assertEqual(lockscreen.lock_at_start(on,tv,sw,"P"),"")
        self.assertEqual(lockscreen.lock_at_start({},tv,sw,"P"),"off")
        self.assertIn("TVWCS session",lockscreen.lock_at_start(on,{},sw,"P"))     # desktop mode: its own login, no lock
        self.assertIn("TVWCS session",lockscreen.lock_at_start(on,tv,which_of(),"P"))
        for status in ("NP","L"): self.assertIn("password",lockscreen.lock_at_start(on,tv,sw,status))
        self.assertEqual(lockscreen.lock_at_start(on,tv,sw,""),"")               # passwd -S could not tell: lock
    def test_password_status(self):
        from tvwcs.account import password_status
        self.assertEqual(password_status(lambda _a:"htpc P 2026-10-01 0 99999 7 -1\n"),"P")
        self.assertEqual(password_status(lambda _a:"tv L 2026-10-01 0 99999 7 -1\n"),"L")
        self.assertEqual(password_status(lambda _a:""),"")
        def fails(_a): raise OSError("no passwd")
        self.assertEqual(password_status(fails),"")
    def test_the_session_config_runs_it_before_tvwcs(self):
        from pathlib import Path
        conf=(Path(__file__).resolve().parents[2]/"data"/"tvwcs.conf").read_text().splitlines()
        self.assertLess(conf.index("exec /usr/bin/tvwcs lock-at-start"),conf.index("exec /usr/bin/tvwcs"))

if __name__=="__main__": unittest.main()
