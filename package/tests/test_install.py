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
if __name__=="__main__": unittest.main()
