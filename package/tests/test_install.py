"""install.sh in a throwaway home folder: where it installs, the include line it adds or moves, the old location
it migrates from, and the window manager config it can create. Skipped outside the repository (no scripts/)."""
import os, pty, select, subprocess, tempfile, time, unittest
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
if __name__=="__main__": unittest.main()
