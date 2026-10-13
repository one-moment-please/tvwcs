import unittest
from tvwcs.system_actions import SYSTEM_ACTIONS, command_for, lock_command, logout_command

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
        self.assertEqual(lock_command("",{},have(set())),["loginctl","lock-session"])
        self.assertEqual(lock_command("",{"SWAYSOCK":"/s"},have({"swaymsg","swaylock","i3lock"}))[0],"swaylock")
    def test_logout_command(self):
        self.assertEqual(logout_command({},lambda c:None),["i3-msg","exit"])
        self.assertEqual(logout_command({"SWAYSOCK":"/s"},lambda c:"/x"),["swaymsg","exit"])
    def test_command_for(self):
        self.assertEqual(command_for("shutdown"),["systemctl","poweroff"]); self.assertEqual(command_for("reboot"),["systemctl","reboot"]); self.assertEqual(command_for("sleep"),["systemctl","suspend"])
        self.assertIsNone(command_for("refresh"))
if __name__=="__main__": unittest.main()
