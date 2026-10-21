"""TVWCS's login screen without GTK: turning it on and off in a pretend root folder (TVWCS_ROOT), its sessions and
automatic login, the greetd protocol against a pretend greetd, what the greeter remembers, and changing a password."""
import json, os, pwd, socket, stat, struct, subprocess, tempfile, threading, unittest
from pathlib import Path
from unittest import mock
from tvwcs import account, greeter, loginscreen

def entry(name, exec_, **keys):
    return "[Desktop Entry]\nName="+name+"\nExec="+exec_+"\n"+"".join(f"{k}={v}\n" for k,v in keys.items())

class RootTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.env=mock.patch.dict(os.environ,{"TVWCS_ROOT":str(self.root)}); self.env.start()
        bin_=self.root/"usr"/"bin"; bin_.mkdir(parents=True)
        for p in ("i3","sway","cinnamon-session"): (bin_/p).write_text("")
        xs=self.root/"usr"/"share"/"xsessions"; xs.mkdir(parents=True); ws=self.root/"usr"/"share"/"wayland-sessions"; ws.mkdir(parents=True)
        (xs/"i3.desktop").write_text(entry("i3","/usr/bin/i3")); (xs/"cinnamon.desktop").write_text(entry("Cinnamon","/usr/bin/cinnamon-session",DesktopNames="X-Cinnamon"))
        (xs/"tvwcs-i3.desktop").write_text(entry("TVWCS (i3)","/usr/bin/i3 -c cfg",DesktopNames="i3"))
        (ws/"sway.desktop").write_text(entry("Sway","/usr/bin/sway")); (xs/"hidden.desktop").write_text(entry("Old","/usr/bin/i3",NoDisplay="true"))
        (ws/"gone.desktop").write_text(entry("Gone","/usr/bin/nothing-here"))
        units=self.root/"lib"/"systemd"/"system"; units.mkdir(parents=True)
        for u in ("lightdm","greetd"): (units/f"{u}.service").write_text("[Unit]\n")
        self.etc=self.root/"etc"; (self.etc/"systemd"/"system").mkdir(parents=True)
        self.out=[]; self.c=loginscreen.Changer(out=self.out.append)
    def tearDown(self): self.env.stop(); self.tmp.cleanup()
    def use(self, unit):
        link=self.etc/"systemd"/"system"/"display-manager.service"
        if link.is_symlink(): link.unlink()
        link.symlink_to(f"/lib/systemd/system/{unit}.service")

    def test_start_session_gives_xsession_the_command_as_one_argument(self):
        """startx splits its client's arguments at spaces (Debian's Xsession then refuses two), so a command such as
        "tvwcs-session i3" reaches Xsession whole."""
        d=Path(self.tmp.name)/"start"; d.mkdir(); script=d/"start-session"; script.write_text(loginscreen.START_SESSION); script.chmod(0o755)
        log=d/"log"
        (d/"startx").write_text('#!/bin/sh\nclient=$1; shift; exec "$client" $*\n'); (d/"startx").chmod(0o755)   # splits, as startx does
        (d/"Xsession").write_text(f'#!/bin/sh\necho "$# $1 $XDG_SESSION_TYPE $XDG_CURRENT_DESKTOP" > "{log}"\n'); (d/"Xsession").chmod(0o755)
        env={"PATH":f"{d}:{os.environ['PATH']}","TVWCS_XSESSION":str(d/"Xsession")}
        subprocess.run([str(script),"x11","i3","/usr/local/bin/tvwcs-session","i3"],env=env,check=True)
        self.assertEqual(log.read_text(),"1 /usr/local/bin/tvwcs-session i3 x11 i3\n")
        (d/"Xsession").unlink()   # no Xsession: the command itself
        (d/"fake-wm").write_text(f'#!/bin/sh\necho "$# $*" > "{log}"\n'); (d/"fake-wm").chmod(0o755)
        subprocess.run([str(script),"x11","-","fake-wm","i3"],env=env,check=True)
        self.assertEqual(log.read_text(),"1 i3\n")

    def test_lifts_greetds_memlock_limit_and_puts_back_the_pam_config_342_wrote(self):
        """pam_ecryptfs crashes greetd's memory-locked worker under the default memlock limit: a systemd drop-in lifts
        it (PAM stays as it is, so eCryptfs homes unlock), and greetd's own PAM config that 3.4.2 set aside comes back."""
        pam=self.etc/"pam.d"; pam.mkdir(); own="#%PAM-1.0\n@include common-auth\n"
        (pam/"greetd").write_text("# Written by TVWCS for its login screen\nauth required pam_unix.so\n"); (pam/"greetd.tvwcs-backup").write_text(own)
        dropin=self.etc/"systemd"/"system"/"greetd.service.d"/"tvwcs-memlock.conf"
        self.use("lightdm"); self.c.enable({},before="lightdm"); self.assertEqual((pam/"greetd").read_text(),own)
        (pam/"greetd").write_text("# Written by TVWCS for its login screen\nauth required pam_unix.so\n"); (pam/"greetd.tvwcs-backup").write_text(own)
        dropin.unlink(); self.c.calls.clear(); self.c.update({})   # updating from 3.4.2
        self.assertEqual((pam/"greetd").read_text(),own); self.assertFalse((pam/"greetd.tvwcs-backup").exists())
        self.assertIn("LimitMEMLOCK=infinity",dropin.read_text()); self.assertIn(["systemctl","daemon-reload"],self.c.calls)
        self.c.calls.clear(); self.c.update({}); self.assertNotIn(["systemctl","daemon-reload"],self.c.calls)   # already there
        self.c.disable("lightdm"); self.assertFalse(dropin.exists()); self.assertEqual((pam/"greetd").read_text(),own)
    def test_sessions_put_tvwcs_first_and_leave_out_hidden_and_missing_ones(self):
        (self.root/"usr"/"share"/"xsessions"/"i3-with-shmlog.desktop").write_text("[Desktop Entry]\nName=i3 (with debug log)\nExec=i3-with-shmlog\nTryExec=i3\n")
        ids=[s["id"] for s in loginscreen.sessions()]
        self.assertEqual(ids,["tvwcs-i3","i3","sway","cinnamon"])
        s={x["id"]:x for x in loginscreen.sessions()}
        self.assertEqual(loginscreen.start_session_argv(s["cinnamon"]),["/usr/local/lib/tvwcs-greeter/start-session","x11","X-Cinnamon","/usr/bin/cinnamon-session"])
        self.assertEqual(s["sway"]["kind"],"wayland")
        # TVWCS's own sessions (TV mode) come first, sway's before i3's
        self.assertEqual(loginscreen.default_session(loginscreen.sessions(),"sway"),"tvwcs-i3")
        self.assertEqual(loginscreen.default_session([{"id":i} for i in ("i3","sway","tvwcs-i3","tvwcs-sway")]),"tvwcs-sway")
        self.assertEqual(loginscreen.default_session([{"id":i} for i in ("i3","sway")]),"sway")
        self.assertEqual(loginscreen.tvwcs_session(loginscreen.sessions(),"i3"),"tvwcs-i3")

    def test_turning_it_on_and_off_goes_back_to_the_login_screen_before(self):
        self.use("lightdm"); (self.etc/"tvwcs").mkdir()
        self.assertEqual(loginscreen.current(),"lightdm"); self.assertFalse(loginscreen.wayland_ok("lightdm"))
        self.c.enable({"accent":"#E81123","theme":"light","scale":"tenfoot"},version="9.9.9")
        self.assertEqual(loginscreen.current(),"tvwcs")
        self.assertEqual(loginscreen.read_look(),{"accent":"#e81123","theme":"light","scale":"tenfoot"})
        lib=self.root/"usr"/"local"/"lib"/"tvwcs-greeter"
        self.assertTrue((lib/"tvwcs"/"ui_greeter.py").is_file()); self.assertEqual((lib/"VERSION").read_text(),"9.9.9\n")
        self.assertTrue(os.access(lib/"start-session",os.X_OK)); self.assertTrue(os.access(lib/"greeter",os.X_OK))
        self.assertIn(["systemctl","disable","lightdm.service"],self.c.calls); self.assertIn(["systemctl","enable","--force","greetd.service"],self.c.calls)
        st=loginscreen.status("9.9.9",{"accent":"#e81123","theme":"light","scale":"tenfoot"})
        self.assertTrue(st["ours"]); self.assertEqual(st["fallback"],"lightdm"); self.assertFalse(st["outdated"]); self.assertFalse(st["look_changed"])
        self.assertTrue(loginscreen.status("10.0.0",{})["outdated"])
        self.c.disable(loginscreen.fallback())
        self.assertEqual(loginscreen.current(),"lightdm"); self.assertFalse(lib.exists())
        self.assertEqual((self.etc/"greetd"/"config.toml").read_text(),loginscreen.GREETD_DEFAULT)   # greetd's own config again, not TVWCS's
        self.assertFalse(loginscreen.greetd_is_ours())
        self.assertIn(["systemctl","enable","--force","lightdm.service"],self.c.calls)

    def test_a_3x_config_gives_the_look_settings_compares_with(self):
        # 3.x saved "use": "tv" with "scale": "tenfoot"; TVWCS 4.0 reads that as Automatic (""), which is TV size here
        import tempfile
        with tempfile.NamedTemporaryFile("w",suffix=".json",delete=False) as f:
            json.dump({"settings":{"use":"tv","scale":"tenfoot","accent":"#E81123"}},f)
        try: raw=loginscreen._settings(f.name)
        finally: os.unlink(f.name)
        self.assertEqual(raw["scale"],"")
        self.assertEqual(loginscreen.look_from(raw),loginscreen.look_from({"scale":"tenfoot","accent":"#e81123"}))
        self.assertEqual(loginscreen.look_from({})["scale"],"tenfoot")

    def test_another_greeters_config_is_kept_and_put_back(self):
        self.use("greetd"); (self.etc/"greetd").mkdir(); conf=self.etc/"greetd"/"config.toml"
        conf.write_text('[default_session]\ncommand = "tuigreet"\nuser = "greeter"\n')
        self.c.enable({})
        cfg=loginscreen.greetd_config(); self.assertEqual(cfg["default_session"]["user"],"greeter"); self.assertTrue(loginscreen.greetd_is_ours(cfg))
        self.assertEqual(loginscreen.fallback(),"greetd")
        self.c.disable("greetd"); self.assertIn("tuigreet",conf.read_text()); self.assertEqual(loginscreen.current(),"greetd")

    def test_greetd_installed_where_there_was_none_turns_off_to_none(self):
        """Installing greetd makes it the login screen (agreety): the one before is what install.sh and Settings pass."""
        self.use("greetd"); (self.etc/"greetd").mkdir(); (self.etc/"greetd"/"config.toml").write_text('[default_session]\ncommand = "agreety --cmd /bin/sh"\n')
        self.c.enable({},before="")
        self.assertEqual((self.etc/"tvwcs"/"previous-login-screen").read_text(),"\n")
        self.assertEqual(loginscreen.fallback(),"lightdm")   # another installed one
        (self.root/"lib"/"systemd"/"system"/"lightdm.service").unlink(); self.assertEqual(loginscreen.fallback(),"")
        self.c.disable("",("tv","i3"))
        self.assertEqual(loginscreen.current(),""); self.assertIn("--autologin tv %I",(self.etc/"systemd"/"system"/"getty@tty1.service.d"/"autologin.conf").read_text())
        self.assertEqual(loginscreen.autologin(),("tv",""))

    def test_automatic_login_where_each_login_screen_keeps_it(self):
        self.use("lightdm"); self.c.enable({})
        self.c.set_autologin("tv","i3")
        cfg=loginscreen.greetd_config()
        self.assertEqual(cfg["initial_session"],{"command":"/usr/local/lib/tvwcs-greeter/start-session x11 i3 /usr/bin/i3","user":"tv"})
        self.assertEqual(loginscreen.autologin(),("tv","i3"))
        self.c.set_autologin("",""); self.assertNotIn("initial_session",loginscreen.greetd_config()); self.assertEqual(loginscreen.autologin(),("",""))
        self.c.disable("lightdm",("tv","tvwcs-i3"))
        self.assertEqual(loginscreen.autologin(),("tv","tvwcs-i3"))
        self.assertIn("autologin-session=tvwcs-i3",(self.etc/"lightdm"/"lightdm.conf.d"/"50-tvwcs-autologin.conf").read_text())
        self.c.set_autologin("",""); self.assertEqual(loginscreen.autologin(),("",""))
        (self.root/"lib"/"systemd"/"system"/"sddm.service").write_text(""); self.use("sddm")
        self.c.set_autologin("tv","sway"); self.assertEqual(loginscreen.autologin(),("tv","sway"))
        self.use("gdm3")
        with self.assertRaises(SystemExit): self.c.set_autologin("tv","i3")
        self.assertFalse(loginscreen.autologin_supported())

    def test_command_line(self):
        self.use("lightdm")
        cfg=self.root/"config.json"; cfg.write_text(json.dumps({"settings":{"accent":"#107c10"}}))
        self.assertEqual(loginscreen.main(["enable","--config",str(cfg),"--autologin","tv","sway","--previous","lightdm"]),0)
        self.assertEqual(loginscreen.read_look()["accent"],"#107c10"); self.assertEqual(loginscreen.autologin(),("tv","sway"))
        self.assertEqual(loginscreen.main(["autologin","--off"]),0); self.assertEqual(loginscreen.autologin(),("",""))
        self.assertEqual(loginscreen.main(["disable"]),0); self.assertEqual(loginscreen.current(),"lightdm")
        self.assertEqual(loginscreen.main(["bogus"]),2)

    def test_root_command_installs_packages_first(self):
        argv=loginscreen.root_command(["enable"],("greetd","cage"))
        self.assertEqual(argv[:2],["sh","-c"]); self.assertEqual(argv[3:7],["sh","2","greetd","cage"])
        self.assertEqual(argv[7:9],["env","PYTHONDONTWRITEBYTECODE=1"]); self.assertEqual(argv[-3:],["-m","tvwcs.loginscreen","enable"])
        with self.assertRaises(ValueError): loginscreen.root_command(["enable"],("bad name",))

class StartLinesTests(unittest.TestCase):
    def test_added_and_removed_like_install_sh(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d); (home/".profile").write_text("export A=1\n")
            loginscreen.set_start_lines("sway",home,"/bin/sh")
            text=(home/".profile").read_text(); self.assertTrue(text.startswith("export A=1\n")); self.assertIn("    exec sway\n",text)
            loginscreen.set_start_lines("i3",home,"/bin/sh")
            text=(home/".profile").read_text(); self.assertEqual(text.count(loginscreen.START_BEGIN),1); self.assertIn("exec startx",text)
            self.assertTrue((home/".xinitrc").read_text().endswith("exec i3\n"))
            loginscreen.set_start_lines("",home,"/bin/sh"); self.assertNotIn("TVWCS",(home/".profile").read_text())

class FakeGreetd:
    """greetd's side of the socket: a password of "right" for tv, after a notice."""
    def __init__(self):
        self.ours,self.theirs=socket.socketpair(); self.got=[]
        threading.Thread(target=self.serve,daemon=True).start()
    def recv(self):
        (n,)=struct.unpack("=I",self.theirs.recv(4)); return json.loads(self.theirs.recv(n))
    def send(self, msg):
        b=json.dumps(msg).encode(); self.theirs.sendall(struct.pack("=I",len(b))+b)
    def serve(self):
        try:
            while True:
                m=self.recv(); self.got.append(m); t=m["type"]
                if t=="create_session": self.user=m["username"]; self.step=0; self.send({"type":"auth_message","auth_message_type":"info","auth_message":"Welcome"})
                elif t=="post_auth_message_response" and self.step==0: self.step=1; self.send({"type":"auth_message","auth_message_type":"secret","auth_message":"Password:"})
                elif t=="post_auth_message_response":
                    ok=self.user=="tv" and m.get("response")=="right"
                    self.send({"type":"success"} if ok else {"type":"error","error_type":"auth_error","description":"pam"})
                else: self.send({"type":"success"})
        except (OSError,struct.error,ValueError): pass

class GreetdTests(unittest.TestCase):
    def test_logs_in_and_starts_the_session(self):
        f=FakeGreetd(); g=greeter.Greetd(sock=f.ours)
        self.assertEqual(greeter.log_in(g,"tv","wrong",["sway"]),"That password is not right. Try again.")
        self.assertEqual(f.got[-1],{"type":"cancel_session"})
        self.assertEqual(greeter.log_in(g,"tv","right",["sway"],["XDG_SESSION_TYPE=wayland"]),"")
        self.assertEqual(f.got[-1],{"type":"start_session","cmd":["sway"],"env":["XDG_SESSION_TYPE=wayland"]})
        self.assertEqual([m["type"] for m in f.got[-4:]],["create_session","post_auth_message_response","post_auth_message_response","start_session"])
        self.assertNotIn("response",f.got[-3])   # nothing answered to the notice
    def test_a_greetd_that_stops_answering_is_reported(self):
        """greetd waits for ever when its worker crashes in PAM: the greeter says so instead of "Logging in…"."""
        a,b=socket.socketpair(); a.settimeout(0.2)
        try: self.assertIn("stopped answering",greeter.log_in(greeter.Greetd(sock=a),"tv","pw",["i3"]))
        finally: a.close(); b.close()
    def test_without_greetd(self):
        with mock.patch.dict(os.environ,{},clear=True):
            with self.assertRaises(greeter.GreetdError): greeter.Greetd()

class GreeterTests(unittest.TestCase):
    def test_users_are_people_with_a_shell(self):
        P=lambda n,uid,gecos,shell:pwd.struct_passwd((n,"x",uid,uid,gecos,"/home/"+n,shell))
        with tempfile.NamedTemporaryFile("w") as shells:
            shells.write("/bin/bash\n/usr/bin/zsh\n"); shells.flush()
            got=greeter.users([P("root",0,"","/bin/bash"),P("tv",1000,"Living Room,,,","/bin/bash"),P("kid",1001,"","/usr/bin/zsh"),
                               P("svc",1002,"","/usr/sbin/nologin"),P("nobody",65534,"","/bin/bash")],shells.name)
        self.assertEqual(got,[("kid","kid"),("tv","Living Room")])
    def test_remembers_each_users_session_and_keyboard(self):
        with tempfile.TemporaryDirectory() as d:
            m=greeter.Memory(d); self.assertEqual(m.keyboard("tv"),"full")   # the full keyboard at first
            m.remember("tv","sway","digits"); m2=greeter.Memory(d)
            self.assertEqual((m2.last_user,m2.session("tv"),m2.keyboard("tv")),("tv","sway","digits"))
            self.assertEqual(m2.keyboard("other"),"full")
            (Path(d)/"state.json").write_text("not json"); self.assertEqual(greeter.Memory(d).last_user,"")

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
