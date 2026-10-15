"""install.sh in a throwaway home folder: where it installs, the include line it adds or moves, the old location
it migrates from, the window manager config it can create, and its two setups (this computer only for TVWCS, or
TVWCS next to other desktops in a session of its own). Skipped outside the repository (no scripts/)."""
import json, os, pty, select, shutil, subprocess, tempfile, time, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/"scripts"/"install.sh"
KEYCODES="""# WARNING
# WARNING: This configuration file is a template for the i3-config-wizard.
# WARNING

# i3 config file (v4)
set $mod Mod1
bindcode $mod+36 exec i3-sensible-terminal
"""
SWAY="# Default config for sway\nset $mod Mod4\nbindsym $mod+Return exec $term\n"

@unittest.skipUnless(SCRIPT.is_file(),"install.sh is only in the repository")
class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.home=Path(self.tmp.name)/"home user"   # a space, to test quoting
        self.home.mkdir(); etc=Path(self.tmp.name)/"etc"
        (etc/"i3").mkdir(parents=True); (etc/"i3"/"config.keycodes").write_text(KEYCODES)
        (etc/"sway").mkdir(); (etc/"sway"/"config").write_text(SWAY)
        # /usr/share stand-in: an icon theme and the Metro font are installed, and there are no other desktop sessions
        self.share=Path(self.tmp.name)/"share"; (self.share/"icons"/"Adwaita").mkdir(parents=True)
        (self.share/"icons"/"Adwaita"/"index.theme").write_text("[Icon Theme]\nName=Adwaita\n")
        (self.share/"fonts"/"truetype"/"open-sans").mkdir(parents=True); (self.share/"fonts"/"truetype"/"open-sans"/"OpenSans-Regular.ttf").write_text("")
        self.bindir=Path(self.tmp.name)/"usr-local-bin"
        self.env={"PATH":os.environ["PATH"],"HOME":str(self.home),"TVWCS_ETC":str(etc),"TVWCS_NO_RESTART":"1",
                  "TVWCS_WMS":"i3","XDG_RUNTIME_DIR":str(Path(self.tmp.name)/"run"),"TVWCS_SETUP":"dedicated",
                  "TVWCS_SHARE":str(self.share),"TVWCS_BINDIR":str(self.bindir)}
        self.dest=self.home/".local"/"share"/"tvwcs"; self.i3=self.home/".config"/"i3"/"config"
    def tearDown(self): self.tmp.cleanup()
    def run_install(self,**env):
        p=subprocess.run(["sh",str(SCRIPT)],env={**self.env,**env},stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=60)
        self.assertEqual(p.returncode,0,p.stderr); return p.stdout
    def write_i3(self,text): self.i3.parent.mkdir(parents=True,exist_ok=True); self.i3.write_text(text)

    def test_installs_into_local_share_and_points_the_fragment_at_it(self):
        out=self.run_install()
        self.assertTrue((self.dest/"bin"/"tvwcs").is_file() and (self.dest/"tvwcs"/"main.py").is_file(),out)
        conf=(self.dest/"tvwcs.conf").read_text()
        self.assertIn(f"exec --no-startup-id '{self.dest}/bin/tvwcs'\n",conf); self.assertNotIn(".config/i3/tvwcs",conf.split("# ---")[1])
        self.assertIn(f"'{self.dest}/bin/tvwcs' toggle",(self.home/".config"/"tvwcs"/"hotkeys.conf").read_text())
        self.assertIn("No i3 config found",out); self.assertFalse(self.i3.exists())   # never created without a terminal
    def test_lists_the_control_panel_with_the_applications(self):
        self.run_install()
        entry=(self.home/".local"/"share"/"applications"/"com.tvwcs.ControlPanel.desktop").read_text()
        self.assertIn(f'\nExec="{self.dest}/bin/tvwcs" settings\n',entry)   # quoted: this home folder has a space
        self.assertIn(f'\nExec="{self.dest}/bin/tvwcs" settings network\n',entry); self.assertNotIn("Exec=tvwcs",entry)
        self.assertIn("Categories=Settings;System;",entry); self.assertIn(f"Icon={self.dest}/tvwcs-settings.svg",entry); self.assertTrue((self.dest/"com.tvwcs.ControlPanel.desktop").is_file())
        self.assertIn("\nName=TVWCS Settings\n",entry); self.assertIn("\nNotShowIn=GNOME;KDE;\n",entry)   # not next to GNOME's or KDE's own Settings
    def test_adds_the_include_line_when_allowed_and_only_once(self):
        self.write_i3("set $mod Mod4\n")
        out=self.run_install(); self.assertIn("Left",out); self.assertEqual(self.i3.read_text(),"set $mod Mod4\n")   # no terminal: no change
        self.run_install(TVWCS_ASSUME_YES="1")
        text=self.i3.read_text(); self.assertTrue(text.endswith('include ~/.local/share/tvwcs/tvwcs.conf\n'),text)
        self.assertEqual((self.i3.parent/"config.tvwcs-backup").read_text(),"set $mod Mod4\n")
        out=self.run_install(TVWCS_ASSUME_YES="1"); self.assertIn("already includes",out); self.assertEqual(self.i3.read_text(),text)
    def test_moves_an_install_from_the_old_location(self):
        legacy=self.home/".config"/"i3"/"tvwcs"; (legacy/"bin").mkdir(parents=True); (legacy/"bin"/"tvwcs").write_text("old")
        (legacy/"tvwcs.conf.bak").write_text("hand edits")
        self.write_i3("bar {}\ninclude ~/.config/i3/tvwcs/tvwcs.conf\nexec foo\n")
        hk=self.home/".config"/"tvwcs"/"hotkeys.conf"; hk.parent.mkdir(parents=True)
        hk.write_text(f"bindsym F2 exec --no-startup-id '{legacy}/bin/tvwcs' toggle\n")
        out=self.run_install()   # no terminal, no consent: everything still works from the old place
        self.assertIn("Change its TVWCS include line",out); self.assertIn("Kept the old copy",out); self.assertTrue(legacy.exists())
        self.assertIn(f"'{self.dest}/bin/tvwcs' toggle",hk.read_text())
        sway=self.home/".config"/"sway"/"config"; sway.parent.mkdir(parents=True); sway.write_text("set $mod Mod4\n")
        out=self.run_install(TVWCS_MIGRATE="1",TVWCS_WMS="i3 sway")   # the in-app updater, after you agreed to the move
        self.assertEqual(self.i3.read_text(),'bar {}\ninclude ~/.local/share/tvwcs/tvwcs.conf\nexec foo\n')
        self.assertEqual(sway.read_text(),"set $mod Mod4\n")   # moving never adds TVWCS where it was not
        self.assertFalse(legacy.exists(),out); self.assertEqual((self.dest/"tvwcs.conf.bak").read_text(),"hand edits")
    def test_custom_destination_is_written_absolute(self):
        self.write_i3(""); dest=Path(self.tmp.name)/"opt"/"tvwcs"
        self.run_install(TVWCS_ASSUME_YES="1",TVWCS_DEST=str(dest))
        self.assertIn(f'include "{dest}/tvwcs.conf"' if " " in str(dest) else f"include {dest}/tvwcs.conf",self.i3.read_text())
        self.assertIn(f"exec --no-startup-id '{dest}/bin/tvwcs'",(dest/"tvwcs.conf").read_text())

    def converse(self,answers,prompts=None,**env):
        """Run install.sh on a terminal, answering each prompt in turn; a prompt containing a key of `prompts` gets
        that answer instead, wherever it comes (the prompts before it depend on the computer)."""
        pid,fd=pty.fork()
        if pid==0:
            os.chdir(self.tmp.name); os.execvpe("sh",["sh",str(SCRIPT)],{**self.env,**env})
        out=b""; pending=list(answers); deadline=time.time()+60
        while time.time()<deadline:
            r,_,_=select.select([fd],[],[],0.2)
            if r:
                try: chunk=os.read(fd,4096)
                except OSError: break
                if not chunk: break
                out+=chunk
                if out.rstrip().endswith((b"]",b"]:",b"):")):   # a prompt: the next answer (or "n" when none is left)
                    last=out.rstrip().rsplit(b"\n",1)[-1].decode(errors="replace")
                    fixed=next((a for k,a in (prompts or {}).items() if k in last),None)
                    answer=fixed if fixed is not None else (pending.pop(0) if pending else "n")
                    os.write(fd,(answer+"\n").encode()); out+=b"\n"
        if time.time()>=deadline: os.kill(pid,9)   # still asking (an answer it keeps refusing): fail rather than hang
        _pid,status=os.waitpid(pid,0); self.status=os.waitstatus_to_exitcode(status); return out.decode(errors="replace")
    def test_asks_once_whether_it_is_used_on_a_tv_or_a_desktop(self):
        config=self.home/".config"/"tvwcs"/"config.json"
        use=lambda answer:{"1 (TV) or 2 (desktop)":answer}   # every other prompt: no
        out=self.converse([],use("2"))   # a desktop monitor
        self.assertIn("Will TVWCS be used on a TV or on a desktop monitor?",out)
        s=json.loads(config.read_text())["settings"]
        self.assertEqual((s["use"],s["scale"],s["always_new_workspace"],s["open_in_new_workspace"]),("desktop","desktop",False,False))
        out=self.converse([]); self.assertNotIn("Will TVWCS be used",out)   # answered: not asked again
        config.unlink(); self.converse([],use(""))   # Enter: a TV
        s=json.loads(config.read_text())["settings"]
        self.assertEqual((s["use"],s["scale"],s["always_new_workspace"],s["open_in_new_workspace"]),("tv","tenfoot",True,True))
        config.unlink(); out=self.run_install(); self.assertNotIn("Will TVWCS be used",out); self.assertFalse(config.exists())   # no terminal
    def test_creates_an_i3_config_with_the_chosen_mod_key_and_layout(self):
        out=self.converse(["y","2","n","de nodeadkeys","y"])   # create? / Alt / not the current layout / German / add the include
        text=self.i3.read_text()
        self.assertIn("set $mod Mod1",text); self.assertNotIn("WARNING",text); self.assertIn("bindcode $mod+36",text)
        self.assertIn("exec_always --no-startup-id setxkbmap -layout de -variant nodeadkeys",text)
        self.assertTrue(text.rstrip().endswith('include ~/.local/share/tvwcs/tvwcs.conf'),out)
    def test_creates_a_sway_config_and_rejects_an_unknown_layout(self):
        if not Path("/usr/share/X11/xkb/rules/evdev.lst").is_file(): self.skipTest("no XKB layout list here")
        out=self.converse(["y","1","n","zz","fr","y"],TVWCS_WMS="sway")   # ... unknown layout, then French, then add the include
        self.assertIn("not a keyboard layout",out)
        text=(self.home/".config"/"sway"/"config").read_text()
        self.assertIn("set $mod Mod4",text); self.assertIn("input type:keyboard {\n    xkb_layout fr\n}",text); self.assertIn("tvwcs.conf",text)
    def fake_tools(self,listing=""):
        """A fake sudo / visudo / id in front of PATH: a user called tv (uid 1000) whom sudo lets do what it is asked."""
        bin_=Path(self.tmp.name)/"fakebin"; bin_.mkdir(exist_ok=True)
        (bin_/"id").write_text('#!/bin/sh\ncase "$1" in -un) echo tv ;; -u) echo 1000 ;; *) exec /usr/bin/id "$@" ;; esac\n')
        (bin_/"sudo").write_text('#!/bin/sh\n'
            f'case "$1" in -k) exit 0 ;; -n) [ "$2" = -l ] && [ -f "{bin_}/listing" ] && {{ cat "{bin_}/listing"; exit 0; }}; exit 1 ;; esac\n'
            f'[ "$1" = visudo ] && {{ echo "visudo $*" >> "{bin_}/log"; exit 0; }}\nexec "$@"\n')
        for f in ("id","sudo"): (bin_/f).chmod(0o755)
        if listing: (bin_/"listing").write_text(listing)
        return {"PATH":f"{bin_}:{self.env['PATH']}"},bin_
    def test_offers_a_narrow_no_password_sudo_rule_only_on_yes(self):
        if not any(Path(d,"systemctl").exists() for d in ("/usr/bin","/bin","/usr/sbin","/sbin","/usr/local/bin","/usr/local/sbin")): self.skipTest("no systemctl here")
        env,bin_=self.fake_tools(); rules=Path(self.env["TVWCS_ETC"])/"sudoers.d"
        self.converse(["n","n"],**env)   # no i3 config; no rule
        self.assertFalse(rules.exists())
        out=self.converse(["n","y"],**env)
        rule=rules/"zz-tvwcs-power-tv"   # "zz-": read after the user's other rules, since the last match wins
        self.assertTrue(rule.is_file(),out); self.assertEqual(rule.stat().st_mode & 0o777,0o440)
        text=rule.read_text(); self.assertIn("visudo -cf",(bin_/"log").read_text())
        self.assertIn("tv ALL=(root) NOPASSWD: TVWCS_POWER_TV\n",text)
        alias=next(l for l in text.splitlines() if l.startswith("Cmnd_Alias TVWCS_POWER_TV = "))
        for entry in alias.split(" = ",1)[1].split(", "):   # only these programs, each with exactly its arguments
            prog,_,args=entry.partition(" ")
            self.assertEqual(Path(prog).name,"systemctl",entry)
            self.assertIn(args,{"suspend","reboot","poweroff"},entry)
    def test_says_when_the_rule_is_already_in_effect(self):
        first=next((f"{d}/systemctl suspend" for d in ("/usr/bin","/bin","/usr/sbin","/sbin","/usr/local/bin","/usr/local/sbin") if Path(d,"systemctl").exists()),None)
        if first is None: self.skipTest("no systemctl here")
        env,_=self.fake_tools("User tv may run the following commands on box:\n    (ALL) ALL\n    (root) NOPASSWD: "+first+", /usr/sbin/reboot \"\"\n")
        self.assertIn("already work without a password",self.converse(["n"],**env))
        env,_=self.fake_tools("User tv may run the following commands on box:\n    (root) NOPASSWD: "+first+"\n    (ALL) ALL\n")   # a later rule wins
        self.assertIn("without asking for your password?",self.converse(["n","n"],**env))
    def autologin_tools(self,*programs,shell="/bin/bash"):
        """fake_tools, plus a systemd system, a login shell for tv, and pretend programs (i3, startx, sway, a login screen).
        systemctl, sv and chvt only write down how they were called; nobody is logged in on a console."""
        env,bin_=self.fake_tools()
        for name in programs: (bin_/name).touch(); (bin_/name).chmod(0o755)
        for name in ("systemctl","sv","chvt"): (bin_/name).write_text(f'#!/bin/sh\necho "{name} $*" >> "{bin_}/calls"\n'); (bin_/name).chmod(0o755)
        self.calls=bin_/"calls"; self.who=bin_/"who.txt"
        (bin_/"who").write_text(f'#!/bin/sh\ncat "{self.who}" 2>/dev/null; exit 0\n'); (bin_/"who").chmod(0o755)
        (bin_/"getent").write_text(f'#!/bin/sh\necho "tv:x:1000:1000::{self.home}:{shell}"\n'); (bin_/"getent").chmod(0o755)
        run=Path(self.tmp.name)/"fakerun"; (run/"systemd"/"system").mkdir(parents=True,exist_ok=True)
        return {**env,"TVWCS_RUN":str(run)},Path(self.env["TVWCS_ETC"])/"systemd"/"system"/"getty@tty1.service.d"/"autologin.conf"
    def test_offers_to_log_in_and_start_i3_at_boot_when_there_is_no_login_screen(self):
        env,override=self.autologin_tools("i3","startx")
        out=self.converse(["n","n","n"],**env)   # no i3 config; no power rule; no automatic login
        self.assertIn("Log in as tv automatically when it starts, and start i3?",out); self.assertFalse(override.exists())
        out=self.converse(["n","n","y"],**env)
        text=override.read_text()
        self.assertEqual(self.calls.read_text(),"systemctl restart getty@tty1.service\nchvt 1\n",out)   # started now, on the screen
        config=json.loads((self.home/".config"/"tvwcs"/"config.json").read_text())
        self.assertEqual(config["settings"]["startup"]["mode"],"menu")   # TVWCS opens its Quick Menu at log-in
        self.assertIn("does not include TVWCS",out)   # the i3 config was not created
        self.assertIn("ExecStart=\n",text); self.assertIn("--autologin tv %I $TERM",text); self.assertIn("-o '-p -f -- \\\\u'",text)
        profile=(self.home/".profile").read_text()
        self.assertIn('[ "$(tty)" = /dev/tty1 ] && command -v startx >/dev/null 2>&1; then\n    exec startx\nfi',profile)
        self.assertEqual((self.home/".xinitrc").read_text().splitlines()[-1],"exec i3")
        self.assertEqual(subprocess.run(["sh","-n",str(self.home/".profile")]).returncode,0)
        out=self.converse(["n","n"],**env)   # asked again: it is already set up
        self.assertIn("already logs someone in",out); self.assertEqual((self.home/".profile").read_text(),profile)
    def test_starts_sway_from_zsh_and_replaces_its_own_lines(self):
        env,override=self.autologin_tools("i3","startx","sway",shell="/usr/bin/zsh")
        zprofile=self.home/".zprofile"; zprofile.write_text("export EDITOR=vi\n")
        self.converse(["n","n","n","y","2"],TVWCS_WMS="i3 sway",**env)   # no i3 or sway config; no power rule; yes; sway
        self.assertTrue(override.exists()); override.unlink()
        self.converse(["n","n","n","y","2"],TVWCS_WMS="i3 sway",**env)
        text=zprofile.read_text()
        self.assertTrue(text.startswith("export EDITOR=vi\n")); self.assertEqual(text.count("exec sway"),1); self.assertNotIn("startx",text)
    def test_does_not_take_over_a_console_someone_is_logged_in_on(self):
        env,override=self.autologin_tools("i3","startx")
        self.who.write_text("tv       tty1         2026-10-14 21:00\n")
        out=self.converse(["n","n","y"],**env)
        self.assertTrue(override.exists()); self.assertIn("Someone is logged in",out); self.assertFalse(self.calls.exists())
    def test_no_offer_with_a_login_screen_or_without_a_terminal(self):
        env,override=self.autologin_tools("i3","startx","lightdm")
        self.assertNotIn("automatically when it starts",self.converse(["n","n","y"],**env))
        env,override=self.autologin_tools("i3","startx")
        self.run_install(**env); self.assertFalse(override.exists())
    def test_without_systemd_the_automatic_login_is_not_offered(self):
        """Only systemd systems are supported (TODO.md has what runit and OpenRC would need): it says so, and changes nothing."""
        env,override=self.autologin_tools("i3","startx","sv")
        empty=Path(self.tmp.name)/"norun"; empty.mkdir(); env["TVWCS_RUN"]=str(empty)   # no systemd
        conf=Path(self.env["TVWCS_ETC"])/"sv"/"agetty-tty1"/"conf"; conf.parent.mkdir(parents=True); conf.write_text('GETTY_ARGS="--noclear"\n')
        out=self.converse(["n","n","y"],**env)
        self.assertIn("does not run systemd",out); self.assertIn("needs systemd, so it was not offered",out)
        self.assertNotIn("automatically when it starts",out); self.assertFalse(override.exists()); self.assertFalse(self.calls.exists())
        self.assertEqual(conf.read_text(),'GETTY_ARGS="--noclear"\n'); self.assertFalse((self.home/".profile").exists())
    def test_reaches_a_running_i3_by_its_socket_from_an_ssh_login(self):
        """Over SSH there is no DISPLAY or I3SOCK: i3 is found by the socket in the user's runtime folder."""
        import socket
        env,bin_=self.fake_tools()
        (bin_/"i3-msg").write_text(f'#!/bin/sh\necho "$*" >> "{bin_}/i3-msg.log"\n'); (bin_/"i3-msg").chmod(0o755)
        sock_dir=Path(self.env["XDG_RUNTIME_DIR"])/"i3"; sock_dir.mkdir(parents=True)
        sock=socket.socket(socket.AF_UNIX); sock.bind(str(sock_dir/"ipc-socket.42")); self.addCleanup(sock.close)
        self.write_i3("# i3 config file (v4)\n")
        out=self.run_install(TVWCS_ASSUME_YES="1",SSH_CONNECTION="10.0.0.2 50000 10.0.0.3 22",**env)
        self.assertIn("Reloaded i3.",out); self.assertNotIn("no terminal",out)
        self.assertIn(f"-s {sock_dir}/ipc-socket.42 -q reload",(bin_/"i3-msg.log").read_text())
    def test_says_how_to_be_asked_over_ssh_without_a_terminal(self):
        self.assertIn("ssh -t",self.run_install(SSH_CONNECTION="10.0.0.2 50000 10.0.0.3 22"))
    def test_offers_pipewire_when_there_is_no_sound_server(self):
        env,bin_=self.fake_tools(); (Path(self.env["TVWCS_ETC"])/"os-release").write_text("ID=debian\n")
        sysbin=Path(self.tmp.name)/"sysbin"; sysbin.mkdir()   # the system's programs, less any sound server it has
        for d in os.environ["PATH"].split(":"):
            for prog in (Path(d).iterdir() if Path(d).is_dir() else ()):
                if prog.name not in ("pipewire","pulseaudio") and not (sysbin/prog.name).exists() and prog.is_file() and os.access(prog,os.X_OK): (sysbin/prog.name).symlink_to(prog)
        env["PATH"]=f"{bin_}:{sysbin}"
        (bin_/"apt-get").write_text(f'#!/bin/sh\necho "apt-get $*" >> "{bin_}/apt"\n'); (bin_/"apt-get").chmod(0o755)
        out=self.converse(["y","n","n","n","n"],**env)
        self.assertRegex(out,r"pipewire pipewire-pulse wireplumber dbus-user-session +PipeWire: sound")
        self.assertIn("pipewire pipewire-pulse wireplumber",(bin_/"apt").read_text(),out)
    def without_gtk(self,bin_):
        """These tests need neither window manager here, and GTK missing (so the package list is always asked about)."""
        if shutil.which("i3") or shutil.which("sway"): self.skipTest("i3 or sway is installed here")
        (bin_/"python3").write_text('#!/bin/sh\nexit 1\n'); (bin_/"python3").chmod(0o755)
    def test_offers_to_install_i3_then_to_start_it_at_boot(self):
        """Neither i3 nor sway: Enter installs the recommended i3 (with Xorg and startx), then the automatic login is offered."""
        env,override=self.autologin_tools()
        bin_=Path(env["PATH"].split(":")[0]); etc=Path(self.env["TVWCS_ETC"]); self.without_gtk(bin_)
        (etc/"os-release").write_text("ID=debian\n")
        (bin_/"apt-get").write_text(f'#!/bin/sh\necho "apt-get $*" >> "{bin_}/apt"\n'
            f'case "$*" in *install*) for p in i3 startx; do printf "#!/bin/sh\\n" > "{bin_}/$p"; chmod +x "{bin_}/$p"; done ;; esac\n')
        (bin_/"apt-get").chmod(0o755)
        out=self.converse(["","n","n","n","y"],TVWCS_WMS="",TVWCS_X_SERVER="",**env)   # Enter: i3; not the other packages; no i3 config; no power rule; yes to the automatic login
        apt=(bin_/"apt").read_text()
        self.assertIn("apt-get update -q\n",apt); self.assertIn("install -y i3 xserver-xorg xinit xdotool x11-xserver-utils",apt)
        self.assertIn("1) i3 with Xorg (recommended)",out); self.assertIn("Installed i3.",out)
        self.assertTrue(override.exists(),out); self.assertIn("exec startx",(self.home/".profile").read_text())
    def test_installs_i3_without_xorg_when_xlibre_is_installed(self):
        """XLibre is a fork of Xorg that replaces it: i3 is installed for it, and the Xorg server is neither offered nor installed."""
        env,_override=self.autologin_tools()
        bin_=Path(env["PATH"].split(":")[0]); etc=Path(self.env["TVWCS_ETC"]); self.without_gtk(bin_)
        (etc/"os-release").write_text("ID=debian\n")
        (bin_/"Xlibre").write_text("#!/bin/sh\necho 'XLibre X Server 25.0'\n"); (bin_/"Xlibre").chmod(0o755)
        (bin_/"apt-get").write_text(f'#!/bin/sh\necho "apt-get $*" >> "{bin_}/apt"\n'); (bin_/"apt-get").chmod(0o755)
        out=self.converse(["","n","n","n","n"],TVWCS_WMS="",**env)
        self.assertIn("1) i3, for the XLibre already installed (recommended)",out); self.assertNotIn("with Xorg",out)
        apt=(bin_/"apt").read_text()
        self.assertIn("install -y i3 xinit xdotool x11-xserver-utils\n",apt); self.assertNotIn("xserver-xorg ",apt)
    def test_install_offer_can_be_declined_and_sway_chosen(self):
        env,_override=self.autologin_tools()
        bin_=Path(env["PATH"].split(":")[0]); (Path(self.env["TVWCS_ETC"])/"os-release").write_text("ID=debian\n"); self.without_gtk(bin_)
        (bin_/"apt-get").write_text(f'#!/bin/sh\necho "apt-get $*" >> "{bin_}/apt.log"\n'); (bin_/"apt-get").chmod(0o755)
        self.assertIn("Nothing was installed.",self.converse(["3","n","n","n"],TVWCS_WMS="",**env))
        self.assertFalse((bin_/"apt.log").exists())
        self.converse(["2","n","n","n"],TVWCS_WMS="",**env)
        self.assertIn("install -y sway\n",(bin_/"apt.log").read_text())
    def test_unsupported_distribution_says_what_to_install_by_hand(self):
        """Arch, Fedora and the rest are not supported: nothing is installed, and it says what to install and where to read more."""
        env,_override=self.autologin_tools()
        bin_=Path(env["PATH"].split(":")[0]); (Path(self.env["TVWCS_ETC"])/"os-release").write_text("ID=arch\n"); self.without_gtk(bin_)
        (bin_/"pacman").write_text(f'#!/bin/sh\necho "pacman $*" >> "{bin_}/pacman.log"\n'); (bin_/"pacman").chmod(0o755)
        out=self.converse(["n","n","n"],TVWCS_WMS="",**env)
        self.assertEqual(self.status,0,out)
        self.assertEqual(out.count("only install packages on Debian and its family"),1,out); self.assertIn("TODO.md",out)
        self.assertIn("Install i3 (with an X server and startx) or sway yourself",out); self.assertNotIn("Install one now?",out)
        self.assertIn("To install them:  install with your package manager: PyGObject GTK4",out); self.assertNotIn("Install them now?",out)
        self.assertFalse((bin_/"pacman.log").exists()); self.assertTrue((self.dest/"TODO.md").is_file())
    def test_lists_an_icon_theme_and_the_metro_font_when_missing(self):
        env,bin_=self.fake_tools(); os_release=Path(self.env["TVWCS_ETC"])/"os-release"; os_release.write_text("ID=debian\n")
        shutil.rmtree(self.share/"icons"); shutil.rmtree(self.share/"fonts")
        out=self.run_install(**env)
        self.assertRegex(out,r"adwaita-icon-theme +icons for apps and buttons"); self.assertRegex(out,r"fonts-open-sans +Open Sans: the font")
        papirus=self.home/".local"/"share"/"icons"/"Papirus"; papirus.mkdir(parents=True); (papirus/"index.theme").write_text("")   # the user's own theme counts
        self.assertNotIn("icons for apps",self.run_install(**env))
    def test_lists_missing_packages_with_their_use_and_installs_them(self):
        env,bin_=self.fake_tools(); (Path(self.env["TVWCS_ETC"])/"os-release").write_text("ID=debian\n")
        for tool in ("i3","pactl","bluetoothctl","nmcli","xrandr","xdotool","pipewire","unclutter","xprintidle"): (bin_/tool).write_text("#!/bin/sh\n"); (bin_/tool).chmod(0o755)
        (bin_/"python3").write_text('#!/bin/sh\nexit 1\n'); (bin_/"python3").chmod(0o755)   # no GTK, no VTE
        (bin_/"apt-get").write_text(f'#!/bin/sh\necho "apt-get $*" >> "{bin_}/apt"\n'); (bin_/"apt-get").chmod(0o755)
        out=self.converse(["y","n","n"],**env)   # install; no i3 config; no power rule
        self.assertRegex(out,r"python3-gi gir1\.2-gtk-4\.0 +GTK 4 for Python: TVWCS's windows \(required\)")
        self.assertRegex(out,r"gir1\.2-vte-3\.91 +Settings: the terminal page")
        self.assertNotIn("Settings: sound",out); self.assertNotIn("xdotool",out)   # installed here, so not listed
        self.assertIn("apt-get install -y python3-gi gir1.2-gtk-4.0 gir1.2-vte-3.91\n",(bin_/"apt").read_text())
        (bin_/"unclutter").unlink()
        if not shutil.which("unclutter",path=self.env["PATH"]):   # a computer with unclutter installed has it anyway
            self.assertRegex(self.converse(["n","n","n"],**env),r"unclutter-xfixes +hides the mouse pointer after 3 seconds")
        (bin_/"unclutter").write_text("#!/bin/sh\n"); (bin_/"unclutter").chmod(0o755)
        out=self.converse(["n","n","n"],**env)
        self.assertIn("To install them:  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-vte-3.91",out)

    # ---------------------------------------------------------------- the two setups
    def test_suggests_a_setup_from_what_is_found_and_remembers_the_choice(self):
        ask={"Choose 1 (only TVWCS) or 2 (next to other desktops)":""}   # Enter: the suggestion
        out=self.converse([],ask,TVWCS_SETUP="")
        self.assertIn("Found: no login screen, no desktop sessions",out); self.assertIn("other desktops) [1]:",out)
        self.assertIn("Setting this computer up for TVWCS only.",out)
        setup=self.home/".config"/"tvwcs"/"setup"; self.assertEqual(setup.read_text(),"dedicated\n")
        setup.unlink(); (self.share/"xsessions").mkdir(); (self.share/"xsessions"/"gnome.desktop").write_text("[Desktop Entry]\n")
        (self.share/"xsessions"/"i3.desktop").write_text("[Desktop Entry]\n")   # i3's own session is not another desktop
        out=self.converse([],ask,TVWCS_SETUP="")
        self.assertIn("desktop sessions (gnome)",out); self.assertIn("other desktops) [2]:",out); self.assertEqual(setup.read_text(),"alongside\n")
        out=self.run_install(TVWCS_SETUP=""); self.assertIn("Setting TVWCS up next to your other desktops.",out)   # no terminal: as last time
        out=self.converse([],{"Choose 1 (only TVWCS)":"1"},TVWCS_SETUP=""); self.assertEqual(setup.read_text(),"dedicated\n")
    def test_rejects_an_unknown_setup(self):
        p=subprocess.run(["sh",str(SCRIPT)],env={**self.env,"TVWCS_SETUP":"tablet"},stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=60)
        self.assertEqual(p.returncode,1); self.assertIn("TVWCS_SETUP must be dedicated",p.stderr)
    def alongside(self,*programs,shell="/bin/bash"):
        env,override=self.autologin_tools("i3","startx",*programs,shell=shell)
        return {**env,"TVWCS_SETUP":"alongside"},override
    def assert_hands_off(self,override):
        """Nothing that starts a session by itself: no automatic login, and no start lines in any shell profile."""
        self.assertFalse(override.exists())
        for f in (".profile",".bash_profile",".zprofile",".xinitrc",".config/fish/conf.d/tvwcs-autostart.fish"): self.assertFalse((self.home/f).exists(),f)
    def test_alongside_gives_tvwcs_its_own_session_at_the_login_screen(self):
        env,override=self.alongside("lightdm")
        self.write_i3("set $mod Mod4\nexec --no-startup-id xss-lock -- i3lock\n")
        answers={"Choose 1 or 2 [1]":"1","Use your current keyboard layout":"y","to the login screen?":"y","usual i3 config":"",
                 "1 (TV) or 2 (desktop)":"1"}   # everything else: no
        out=self.converse([],answers,**env)
        self.assertEqual(self.i3.read_text(),"set $mod Mod4\nexec --no-startup-id xss-lock -- i3lock\n")   # your usual config: untouched (Enter is no)
        self.assertIn("Also add TVWCS to your usual i3 config",out); self.assertIn("[y/N]",out)
        session=self.home/".config"/"tvwcs"/"i3-session.conf"; text=session.read_text()
        self.assertIn("set $mod Mod4",text); self.assertIn("bindcode $mod+36",text); self.assertNotIn("WARNING",text)
        self.assertTrue(text.rstrip().endswith("include ~/.local/share/tvwcs/tvwcs.conf"),text)
        entry=(self.share/"xsessions"/"tvwcs-i3.desktop").read_text()
        self.assertIn(f"\nExec={self.bindir}/tvwcs-session i3\n",entry); self.assertIn("\nName=TVWCS (i3)\n",entry); self.assertIn("\nDesktopNames=i3\n",entry)
        wrapper=self.bindir/"tvwcs-session"; self.assertTrue(os.access(wrapper,os.X_OK)); self.assertTrue(os.access(self.dest/"bin"/"tvwcs-session",os.X_OK))
        self.assertEqual(subprocess.run(["sh","-n",str(wrapper)]).returncode,0)
        self.assertIn('choose "TVWCS (i3)" at the login screen',out); self.assert_hands_off(override)
        self.assertEqual(json.loads((self.home/".config"/"tvwcs"/"config.json").read_text())["settings"]["use"],"tv")
        # the wrapper starts i3 with TVWCS's config, and tells TVWCS so
        bin_=Path(env["PATH"].split(":")[0]); log=Path(self.tmp.name)/"i3.log"
        (bin_/"i3").write_text(f'#!/bin/sh\necho "$* $TVWCS_SESSION $TVWCS_SESSION_CONFIG" > "{log}"\n')
        subprocess.run(["sh",str(wrapper),"i3"],env={"PATH":env["PATH"],"HOME":str(self.home)},check=True)
        self.assertEqual(log.read_text(),f"-c {session} i3 {session}\n")
        # again: nothing is written twice, and the root step is skipped when the entry is the same
        out=self.converse([],answers,**env)
        self.assertIn("already lists TVWCS's session",out); self.assertEqual(session.read_text().count("tvwcs.conf"),text.count("tvwcs.conf"))
    def test_alongside_never_sets_up_a_session_that_starts_by_itself(self):
        """Even answering yes to everything, and with no login screen (where the dedicated setup would offer it)."""
        env,override=self.alongside()
        out=self.converse(["y"]*12,TVWCS_WMS="i3 sway",**env)
        self.assert_hands_off(override); self.assertNotIn("automatically when it starts",out)
        self.assertFalse((self.share/"xsessions").exists()); self.assertFalse(self.bindir.exists())   # no login screen: no entry
        self.assertIn(f"startx '{self.dest}/bin/tvwcs-session' i3",out); self.assertIn(f"'{self.dest}/bin/tvwcs-session' sway",out)
        self.assertTrue((self.home/".config"/"tvwcs"/"sway-session.conf").is_file())
        self.write_i3("set $mod Mod4\n"); self.converse(["y"]*12,**env)   # your usual config gets TVWCS only on a clear yes
        self.assertTrue(self.i3.read_text().endswith("include ~/.local/share/tvwcs/tvwcs.conf\n")); self.assert_hands_off(override)
    def test_alongside_without_a_terminal(self):
        """Scripted: TVWCS_ASSUME_YES adds the login screen entry, but never TVWCS to your usual config."""
        env,override=self.alongside("lightdm"); self.write_i3("set $mod Mod4\n")
        out=self.run_install(TVWCS_ASSUME_YES="1",**env)
        self.assertEqual(self.i3.read_text(),"set $mod Mod4\n"); self.assert_hands_off(override)
        self.assertIn("set $mod Mod4",(self.home/".config"/"tvwcs"/"i3-session.conf").read_text())
        self.assertTrue((self.share/"xsessions"/"tvwcs-i3.desktop").is_file(),out)
        moved=self.home/".config"/"tvwcs"/"i3-session.conf"; moved.write_text("set $mod Mod1\ninclude ~/.config/i3/tvwcs/tvwcs.conf\n")
        self.run_install(**env)   # TVWCS's own file is kept pointing at this install without asking
        self.assertEqual(moved.read_text(),"set $mod Mod1\ninclude ~/.local/share/tvwcs/tvwcs.conf\n")
    def test_alongside_says_when_an_earlier_setup_still_logs_in_by_itself(self):
        env,override=self.alongside(); override.parent.mkdir(parents=True); override.write_text("ExecStart=-/sbin/agetty --autologin tv %I\n")
        out=self.converse([],{"Use your current keyboard layout":"y"},**env)
        self.assertIn("still logs someone in by itself",out); self.assertEqual(override.read_text(),"ExecStart=-/sbin/agetty --autologin tv %I\n")
if __name__=="__main__": unittest.main()
