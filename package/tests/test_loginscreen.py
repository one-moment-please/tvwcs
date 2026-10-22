"""The login screen and automatic login without GTK, in a pretend root folder (TVWCS_ROOT): greetd, LightDM and SDDM,
removing TVWCS 4.x's own login screen, and changing a password."""
import json, os, tempfile, unittest
from pathlib import Path
from unittest import mock
from tvwcs import account, loginscreen

OLD_GREETD="""# Written by TVWCS (Settings > User > Login screen). Removing it puts back the config from before.
[terminal]
vt = 7

[default_session]
command = "cage -s -d -- /usr/local/lib/tvwcs-greeter/greeter"
user = "_greetd"

[initial_session]
command = "/usr/local/lib/tvwcs-greeter/start-session x11 i3 /usr/local/bin/tvwcs-session i3"
user = "tv"
"""

class RootTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.env=mock.patch.dict(os.environ,{"TVWCS_ROOT":str(self.root)}); self.env.start()
        ws=self.root/"usr"/"share"/"wayland-sessions"; ws.mkdir(parents=True)
        (ws/"tvwcs-sway.desktop").write_text("[Desktop Entry]\nName=TVWCS\nExec=/usr/bin/tvwcs-session\n")
        self.units=self.root/"lib"/"systemd"/"system"; self.units.mkdir(parents=True)
        (self.units/"greetd.service").write_text("[Unit]\n")
        self.etc=self.root/"etc"; (self.etc/"systemd"/"system").mkdir(parents=True); (self.etc/"greetd").mkdir()
        self.out=[]; self.c=loginscreen.Changer(out=self.out.append)
    def tearDown(self): self.env.stop(); self.tmp.cleanup()
    def use(self, unit):
        link=self.etc/"systemd"/"system"/"display-manager.service"
        if link.is_symlink(): link.unlink()
        link.symlink_to(f"/lib/systemd/system/{unit}.service")
    def old_greeter(self):
        (self.etc/"greetd"/"config.toml").write_text(OLD_GREETD); self.use("greetd")
        lib=self.root/"usr"/"local"/"lib"/"tvwcs-greeter"; lib.mkdir(parents=True); (lib/"greeter").write_text("")
        (self.etc/"tvwcs").mkdir(); (self.etc/"tvwcs"/"login-screen.json").write_text("{}")

    def test_greeter_names(self):
        self.assertEqual(loginscreen.current_greeter({"default_session":{"command":"agreety --cmd /bin/sh"}}),"agreety")
        self.assertEqual(loginscreen.current_greeter({"default_session":{"command":"cage -s -d -- /usr/local/lib/tvwcs-greeter/greeter"}}),"tvwcs")
        self.assertEqual(loginscreen.current_greeter({"default_session":{"command":"cage -s -- gtkgreet"}}),"gtkgreet")
        self.assertEqual(loginscreen.current_greeter({}),"")

    def test_without_a_login_screen_greetd_logs_in_to_tvwcs(self):
        self.assertEqual(loginscreen.active_unit(),"")
        self.c.use_greetd("tv")
        cfg=loginscreen.greetd_config()
        self.assertEqual(cfg["initial_session"],{"command":"/usr/bin/tvwcs-session","user":"tv"})
        self.assertEqual(cfg["default_session"]["command"],"/usr/sbin/agreety --cmd /usr/bin/tvwcs-session")
        self.assertEqual(loginscreen.active_unit(),"greetd"); self.assertEqual(loginscreen.autologin(),("tv","tvwcs-sway"))
        self.assertIn(["systemctl","set-default","graphical.target"],self.c.calls)
        self.assertEqual(loginscreen.name("greetd"),"greetd (text login)")

    def test_another_greetd_greeter_is_kept(self):
        (self.etc/"greetd"/"config.toml").write_text('[terminal]\nvt = 1\n\n[default_session]\ncommand = "tuigreet --cmd sway"\nuser = "greeter"\n')
        self.use("greetd"); self.c.set_autologin("tv")
        cfg=loginscreen.greetd_config()
        self.assertEqual((cfg["default_session"],cfg["terminal"]["vt"]),({"command":"tuigreet --cmd sway","user":"greeter"},1))
        self.assertEqual(loginscreen.autologin(),("tv","tvwcs-sway"))
        self.c.set_autologin(""); self.assertNotIn("initial_session",loginscreen.greetd_config()); self.assertEqual(loginscreen.autologin(),("",""))

    def test_automatic_login_where_each_login_screen_keeps_it(self):
        for u in ("lightdm","sddm"): (self.units/f"{u}.service").write_text("")
        self.use("lightdm"); self.c.set_autologin("tv")
        self.assertIn("autologin-session=tvwcs-sway",(self.etc/"lightdm"/"lightdm.conf.d"/"50-tvwcs-autologin.conf").read_text())
        self.assertEqual(loginscreen.autologin(),("tv","tvwcs-sway"))
        self.c.set_autologin(""); self.assertEqual(loginscreen.autologin(),("",""))
        self.use("sddm"); self.c.set_autologin("tv","sway"); self.assertEqual(loginscreen.autologin(),("tv","sway"))
        self.use("gdm3")
        with self.assertRaises(SystemExit): self.c.set_autologin("tv")
        self.assertFalse(loginscreen.autologin_supported())

    def test_migrating_from_4x_keeps_the_automatic_login_on_greetd(self):
        self.old_greeter(); self.assertTrue(loginscreen.old_greeter())
        self.c.migrate()
        cfg=loginscreen.greetd_config()
        self.assertEqual(cfg["default_session"]["command"],"/usr/sbin/agreety --cmd /usr/bin/tvwcs-session")
        self.assertEqual(cfg["initial_session"],{"command":"/usr/bin/tvwcs-session","user":"tv"})
        self.assertFalse((self.root/"usr"/"local"/"lib"/"tvwcs-greeter").exists()); self.assertFalse((self.etc/"tvwcs"/"login-screen.json").exists())
        self.assertFalse(loginscreen.old_greeter()); self.assertEqual(loginscreen.active_unit(),"greetd")

    def test_migrating_from_4x_switches_to_another_login_screen(self):
        self.old_greeter(); (self.units/"sddm.service").write_text("")
        self.c.migrate()
        self.assertEqual(loginscreen.active_unit(),"sddm"); self.assertEqual(loginscreen.autologin(),("tv","tvwcs-sway"))
        self.assertNotIn("initial_session",loginscreen.greetd_config())   # greetd is off, and has no TVWCS greeter left
        self.assertEqual(loginscreen.current_greeter(),"agreety")

    def test_command_line(self):
        self.assertEqual(loginscreen.main(["greetd","tv"]),0); self.assertEqual(loginscreen.autologin(),("tv","tvwcs-sway"))
        self.assertEqual(loginscreen.main(["autologin","--off"]),0); self.assertEqual(loginscreen.autologin(),("",""))
        self.assertEqual(loginscreen.main(["switch","lightdm"]),1)   # not installed
        self.assertEqual(loginscreen.main(["bogus"]),2)

    def test_root_command_installs_packages_first(self):
        argv=loginscreen.root_command(["greetd","tv"],("greetd",))
        self.assertEqual(argv[:2],["sh","-c"]); self.assertEqual(argv[3:6],["sh","1","greetd"])
        self.assertEqual(argv[6:8],["env","PYTHONDONTWRITEBYTECODE=1"]); self.assertEqual(argv[-4:],["-m","tvwcs.loginscreen","greetd","tv"])
        with self.assertRaises(ValueError): loginscreen.root_command(["greetd"],("bad name",))

class AccountTests(unittest.TestCase):
    def fake_passwd(self, d, accept_new=True):
        """A passwd that asks the usual three questions; "old" is the current password, a short new one is refused."""
        f=Path(d)/"passwd"
        f.write_text("#!/bin/sh\nprintf 'Changing password for tv.\\nCurrent password: '; read -r cur\n"
                     "[ \"$cur\" = old ] || { echo 'passwd: Authentication token manipulation error'; exit 10; }\n"
                     "while :; do printf 'New password: '; read -r new; printf 'Retype new password: '; read -r again\n"
                     "  [ ${#new} -ge 6 ] && break; echo 'BAD PASSWORD: The password is shorter than 6 characters'; done\n"
                     "echo 'passwd: password updated successfully'\n")
        f.chmod(0o755); return str(f)
    def test_changes_the_password_answering_passwd(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.fake_passwd(d)
            self.assertEqual(account.change_password("old","long-enough",argv=(p,)),"")
            self.assertEqual(account.change_password("nope","long-enough",argv=(p,)),"Your current password is not right.")
            self.assertEqual(account.change_password("old","short",argv=(p,)),"BAD PASSWORD: The password is shorter than 6 characters")
            self.assertEqual(account.change_password("old","",argv=(p,)),"The new password is empty.")
    def test_full_name(self):
        self.assertEqual(account.valid_full_name("Living Room"),""); self.assertTrue(account.valid_full_name("a:b"))
        self.assertEqual(account.full_name_argv("tv","Living Room"),["chfn","-f","Living Room","tv"])
        self.assertTrue(account.read().login)

if __name__=="__main__": unittest.main()
