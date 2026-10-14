import unittest
from tvwcs.system_actions import SYSTEM_ACTIONS, command_for, lock_command, logout_command, unavailable_message

class SystemActionTests(unittest.TestCase):
    def test_dialog_contents(self):
        ids=[a.id for a in SYSTEM_ACTIONS]
        self.assertIn("lock",ids); self.assertIn("refresh",ids)
    def test_confirmation_only_for_logout_reboot_shutdown(self):
        self.assertEqual({a.id for a in SYSTEM_ACTIONS if a.confirm},{"logout","reboot","shutdown"})
    def test_lock_prefers_configured_command(self):
        self.assertEqual(lock_command("slock -x",{},lambda c:None),["slock","-x"])
    def test_lock_autodetect_and_fallback(self):
        have=lambda names:(lambda c: "/usr/bin/"+c if c in names else None)
        self.assertEqual(lock_command("",{},have({"i3lock"})),["i3lock","-c","000000"])
        self.assertEqual(lock_command("",{},have({"loginctl"})),["loginctl","lock-session"])
        self.assertIsNone(lock_command("",{},have(set())))   # nothing to lock with: Settings says so
        self.assertEqual(lock_command("",{"SWAYSOCK":"/s"},have({"swaymsg","swaylock","i3lock"}))[0],"swaylock")
    def test_logout_command(self):
        self.assertEqual(logout_command({},lambda c:None),["i3-msg","exit"])
        self.assertEqual(logout_command({"SWAYSOCK":"/s"},lambda c:"/x"),["swaymsg","exit"])
    def test_command_for(self):
        have=lambda names:(lambda c: "/usr/bin/"+c if c in names else None)
        systemd=have({"systemctl","loginctl"})
        self.assertEqual(command_for("shutdown",which=systemd,systemd=True),["systemctl","poweroff"])
        self.assertEqual(command_for("reboot",which=systemd,systemd=True),["systemctl","reboot"]); self.assertEqual(command_for("sleep",which=systemd,systemd=True),["systemctl","suspend"])
        self.assertIsNone(command_for("refresh"))
    def test_power_without_systemd(self):
        have=lambda names:(lambda c: "/usr/bin/"+c if c in names else None)
        elogind=have({"loginctl","reboot","poweroff"})   # Artix, Gentoo, Devuan...: elogind's loginctl
        self.assertEqual([command_for(a,which=elogind,systemd=False) for a in ("sleep","reboot","shutdown")],
                         [["loginctl","suspend"],["loginctl","reboot"],["loginctl","poweroff"]])
        self.assertEqual(command_for("shutdown",which=have({"systemctl","loginctl"}),systemd=False),["loginctl","poweroff"])   # systemctl installed but not in charge
        void=have({"zzz","reboot","poweroff"})   # runit with no elogind
        self.assertEqual([command_for(a,which=void,systemd=False) for a in ("sleep","reboot","shutdown")],[["zzz"],["reboot"],["poweroff"]])
        self.assertIsNone(command_for("sleep",which=have(set()),systemd=False))
        self.assertIn("elogind",unavailable_message("reboot")); self.assertIn("lock_command",unavailable_message("lock"))
if __name__=="__main__": unittest.main()
