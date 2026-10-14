"""install.sh in a throwaway home folder: where it installs, the include line it adds or moves, the old location
it migrates from, and the window manager config it can create. Skipped outside the repository (no scripts/)."""
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
        self.env={"PATH":os.environ["PATH"],"HOME":str(self.home),"TVWCS_ETC":str(etc),"TVWCS_NO_RESTART":"1",
                  "TVWCS_WMS":"i3","XDG_RUNTIME_DIR":str(Path(self.tmp.name)/"run")}
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
        self.assertIn(f'\nExec="{self.dest}/bin/tvwcs" control\n',entry)   # quoted: this home folder has a space
        self.assertIn(f'\nExec="{self.dest}/bin/tvwcs" control network\n',entry); self.assertNotIn("Exec=tvwcs",entry)
        self.assertIn("Categories=Settings;System;",entry); self.assertTrue((self.dest/"com.tvwcs.ControlPanel.desktop").is_file())
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

    def converse(self,answers,**env):
        """Run install.sh on a terminal, answering each prompt in turn."""
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
                    os.write(fd,((pending.pop(0) if pending else "n")+"\n").encode()); out+=b"\n"
        os.waitpid(pid,0); return out.decode(errors="replace")
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
            self.assertIn(Path(prog).name,{"systemctl","loginctl","reboot","poweroff","zzz"},entry)
            self.assertIn(args,{"suspend","reboot","poweroff",'""'},entry)
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
        self.assertTrue(config["settings"]["startup"]["show_menu"])   # TVWCS opens at log-in
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
    def test_runit_console_login(self):
        env,_override=self.autologin_tools("i3","startx","sv")
        empty=Path(self.tmp.name)/"norun"; empty.mkdir(); env["TVWCS_RUN"]=str(empty)   # no systemd
        conf=Path(self.env["TVWCS_ETC"])/"sv"/"agetty-tty1"/"conf"; conf.parent.mkdir(parents=True)
        conf.write_text('if [ -x /sbin/agetty -o -x /bin/agetty ]; then\n\tGETTY_ARGS="--noclear"\nfi\nBAUD_RATE=38400\n')
        self.converse(["n","n","y"],**env)
        self.assertIn("sv restart /var/service/agetty-tty1",self.calls.read_text())
        self.assertEqual(conf.read_text(),'if [ -x /sbin/agetty -o -x /bin/agetty ]; then\n\tGETTY_ARGS="--autologin tv --noclear"\nfi\nBAUD_RATE=38400\n')
        self.assertTrue(Path(f"{conf}.tvwcs-backup").is_file())
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
        out=self.converse(["","n","n","n","y"],TVWCS_WMS="",**env)   # Enter: i3; not the other packages; no i3 config; no power rule; yes to the automatic login
        apt=(bin_/"apt").read_text()
        self.assertIn("apt-get update -q\n",apt); self.assertIn("install -y i3 xserver-xorg xinit xdotool x11-xserver-utils",apt)
        self.assertIn("1) i3 with Xorg (recommended)",out); self.assertIn("Installed i3.",out)
        self.assertTrue(override.exists(),out); self.assertIn("exec startx",(self.home/".profile").read_text())
    def test_install_offer_can_be_declined_and_sway_chosen(self):
        env,_override=self.autologin_tools()
        bin_=Path(env["PATH"].split(":")[0]); (Path(self.env["TVWCS_ETC"])/"os-release").write_text("ID=arch\n"); self.without_gtk(bin_)
        (bin_/"pacman").write_text(f'#!/bin/sh\necho "pacman $*" >> "{bin_}/pacman.log"\n'); (bin_/"pacman").chmod(0o755)
        self.assertIn("Nothing was installed.",self.converse(["3","n","n","n"],TVWCS_WMS="",**env))
        self.assertFalse((bin_/"pacman.log").exists())
        self.converse(["2","n","n","n"],TVWCS_WMS="",**env)
        self.assertEqual((bin_/"pacman.log").read_text().split("\n")[0].split()[:5],["pacman","-S","--needed","--noconfirm","sway"])
    def test_lists_missing_packages_with_their_use_and_installs_them(self):
        env,bin_=self.fake_tools(); (Path(self.env["TVWCS_ETC"])/"os-release").write_text("ID=debian\n")
        for tool in ("i3","pactl","bluetoothctl","nmcli","xrandr","xdotool","pipewire"): (bin_/tool).write_text("#!/bin/sh\n"); (bin_/tool).chmod(0o755)
        (bin_/"python3").write_text('#!/bin/sh\nexit 1\n'); (bin_/"python3").chmod(0o755)   # no GTK, no VTE
        (bin_/"apt-get").write_text(f'#!/bin/sh\necho "apt-get $*" >> "{bin_}/apt"\n'); (bin_/"apt-get").chmod(0o755)
        out=self.converse(["y","n","n"],**env)   # install; no i3 config; no power rule
        self.assertRegex(out,r"python3-gi gir1\.2-gtk-4\.0 +GTK 4 for Python: TVWCS's windows \(required\)")
        self.assertRegex(out,r"gir1\.2-vte-3\.91 +Control Panel: the terminal page")
        self.assertNotIn("Control Panel: sound",out); self.assertNotIn("xdotool",out)   # installed here, so not listed
        self.assertIn("apt-get install -y python3-gi gir1.2-gtk-4.0 gir1.2-vte-3.91\n",(bin_/"apt").read_text())
        out=self.converse(["n","n","n"],**env)
        self.assertIn("To install them:  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-vte-3.91",out)
if __name__=="__main__": unittest.main()
