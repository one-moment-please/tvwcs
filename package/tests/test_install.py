"""install.sh in a throwaway system: a home folder, /etc, /usr/share and /usr/local/bin under a temporary folder, and
stand-ins for sudo, apt-get, wget and the window managers. Covers the questions it asks first, what it then installs
or undoes, the versions it offers, upgrading from 3.x and removing TVWCS. Skipped outside the repository."""
import io, json, os, pty, select, shutil, subprocess, tarfile, tempfile, time, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/"install.sh"
KEYCODES="# WARNING\n# WARNING: a template for the i3-config-wizard.\n# WARNING\n\n# i3 config file (v4)\nset $mod Mod1\nbindcode $mod+36 exec i3-sensible-terminal\n"
SWAY="# Default config for sway\nset $mod Mod4\nbindsym $mod+Return exec $term\n"

def tool(folder, name, body):
    p=Path(folder)/name; p.write_text("#!/bin/sh\n"+body+"\n"); p.chmod(0o755); return p

@unittest.skipUnless((ROOT/"package"/"tvwcs").is_dir(),"install.sh is only tested in the repository")
class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); t=Path(self.tmp.name)
        self.root=t/"root"; self.etc=self.root/"etc"; self.home=t/"home user"; self.home.mkdir()   # a space, to test quoting
        (self.etc/"i3").mkdir(parents=True); (self.etc/"i3"/"config.keycodes").write_text(KEYCODES)
        (self.etc/"sway").mkdir(); (self.etc/"sway"/"config").write_text(SWAY)
        (self.etc/"os-release").write_text("ID=debian\n")
        self.share=self.root/"usr"/"share"; self.share.mkdir(parents=True)
        self.bin=t/"fakebin"; self.bin.mkdir(); self.log=t/"log"
        tool(self.bin,"sudo",'exec "$@"')
        tool(self.bin,"apt-get",f'echo "apt-get $*" >> "{self.log}"; [ -z "$APT_FAILS" ] || {{ [ "$1" = install ] && exit 1; }}; exit 0')
        tool(self.bin,"visudo","exit 0")
        self.downloads=t/"downloads"; self.downloads.mkdir()
        # wget: the file named after the URL's last parts in downloads/ (a/b/c -> a_b_c), else fail
        tool(self.bin,"wget",f'out=$2; url=$3; f=$(echo "$url" | sed "s#^[a-z]*://[^/]*/##; s#[/?=&]#_#g"); [ -f "{self.downloads}/$f" ] || exit 8; cp "{self.downloads}/$f" "$out"')
        self.dest=self.home/".local"/"share"/"tvwcs"
        self.env={"PATH":f"{self.bin}:{os.environ['PATH']}","HOME":str(self.home),"TVWCS_ETC":str(self.etc),"TVWCS_ROOT":str(self.root),
                  "TVWCS_SHARE":str(self.share),"TVWCS_BINDIR":str(self.root/"usr"/"local"/"bin"),"TVWCS_RUN":str(t/"run"),
                  "TVWCS_DEST":str(self.dest),"TVWCS_NO_RESTART":"1","TVWCS_PACKAGES":"","XDG_RUNTIME_DIR":str(t/"rt"),
                  "TVWCS_GITHUB":"https://github.test","TVWCS_API":"https://api.test","TVWCS_UNITS":str(self.root/"lib"/"systemd"/"system"),
                  "LANG":"C.UTF-8"}
        (t/"run"/"systemd"/"system").mkdir(parents=True)
    def tearDown(self): self.tmp.cleanup()
    def wm(self, *names):
        for n in names: tool(self.bin,n,"exit 0")
    def run_install(self, *args, stdin=subprocess.DEVNULL, script=SCRIPT, **env):
        p=subprocess.run(["sh",str(script),*args],env={**self.env,**env},stdin=stdin,capture_output=True,text=True,timeout=60)
        self.out=p.stdout+p.stderr; return p
    def converse(self, answers, prompts=None, script=SCRIPT, **env):
        """Run install.sh on a terminal, answering each prompt in turn; a prompt containing a key of `prompts` gets
        that answer instead, wherever it comes."""
        pid,fd=pty.fork()
        if pid==0:
            os.chdir(self.tmp.name); os.execvpe("sh",["sh",str(script)],{**self.env,**env})
        out=b""; pending=list(answers); deadline=time.time()+60; mark=0
        while time.time()<deadline:
            r,_,_=select.select([fd],[],[],0.2)
            if r:
                try: chunk=os.read(fd,4096)
                except OSError: break
                if not chunk: break
                out+=chunk
                if out[mark:].strip() and out.rstrip().endswith((b"]",b"]:",b"):")):
                    last=out.rstrip().rsplit(b"\n",1)[-1].decode(errors="replace")
                    fixed=next((a for k,a in (prompts or {}).items() if k in last),None)
                    answer=fixed if fixed is not None else (pending.pop(0) if pending else "")
                    os.write(fd,(answer+"\n").encode()); out+=b"\n"; mark=len(out)
        if time.time()>=deadline: os.kill(pid,9)
        _pid,status=os.waitpid(pid,0); self.status=os.waitstatus_to_exitcode(status); self.out=out.decode(errors="replace").replace("\r",""); return self.out
    def release(self, version):
        """A release's tvwcs.tar.gz, as make-release.sh builds it, served at its download URL."""
        buf=io.BytesIO()
        with tarfile.open(fileobj=buf,mode="w:gz") as tar:
            for f in (ROOT/"package"/"tvwcs").glob("*.py"): tar.add(f,f"tvwcs/tvwcs/{f.name}")
            tar.add(ROOT/"package"/"bin"/"tvwcs","tvwcs/bin/tvwcs")
            for f in ("tvwcs.conf","com.tvwcs.ControlPanel.desktop","tvwcs.svg","tvwcs-settings.svg"): tar.add(ROOT/"data"/f,f"tvwcs/{f}")
            tar.add(SCRIPT,"tvwcs/install.sh")
            info=tarfile.TarInfo("tvwcs/VERSION"); data=(version+"\n").encode(); info.size=len(data); tar.addfile(info,io.BytesIO(data))
        (self.downloads/f"one-moment-please_tvwcs_releases_download_v{version}_tvwcs.tar.gz").write_bytes(buf.getvalue())
    def releases(self, latest, rows):
        """GitHub's release list: rows of (version, prerelease)."""
        items=[{"url":"x","tag_name":f"v{v}","name":f"TVWCS {v}","draft":False,"prerelease":pre,"body":'not a "tag_name": "v9.9.9"'} for v,pre in rows]
        (self.downloads/"repos_one-moment-please_tvwcs_releases_per_page_30").write_text(json.dumps(items,indent=2))
        (self.downloads/"repos_one-moment-please_tvwcs_releases_latest").write_text(json.dumps({"tag_name":f"v{latest}","prerelease":False}))
    def version(self): return (ROOT/"VERSION").read_text().strip()

    # ------------------------------------------------------------------ options
    def test_help_and_unknown_options_change_nothing(self):
        p=self.run_install("--help"); self.assertEqual(p.returncode,0); self.assertIn("--missing",p.stdout); self.assertNotIn("set -eu",p.stdout)
        p=self.run_install("--bogus"); self.assertEqual(p.returncode,2)
        self.assertFalse(self.dest.exists())
    def test_missing_lists_the_packages_by_what_they_are_for(self):
        self.wm("sway")
        p=self.run_install("--missing"); self.assertEqual(p.returncode,0,self.out)
        self.assertIn("need\tpython3 python3-gi gir1.2-gtk-4.0 python3-gi-cairo\tTVWCS's windows",p.stdout)
        self.assertIn("need\tsway swayidle swaylock\t",p.stdout); self.assertNotIn("xinit",p.stdout)
        self.assertTrue(all(l.startswith("need\t") for l in p.stdout.splitlines()),p.stdout)
        self.assertNotIn("flatpak",p.stdout)   # Settings > Apps offers Flatpak itself
        self.assertFalse(self.dest.exists()); self.assertFalse((self.home/".config").exists())

    # ------------------------------------------------------------------ without a terminal (the in-app updater)
    def test_without_a_terminal_it_installs_this_package_and_asks_nothing(self):
        self.wm("i3")
        p=self.run_install(); self.assertEqual(p.returncode,0,self.out)
        self.assertEqual((self.dest/"VERSION").read_text().strip(),self.version())
        self.assertIn(f"exec --no-startup-id '{self.dest}/bin/tvwcs'",(self.dest/"tvwcs.conf").read_text())
        session=(self.home/".config"/"tvwcs"/"i3-session.conf").read_text()
        self.assertTrue(session.rstrip().endswith("include ~/.local/share/tvwcs/tvwcs.conf"),session)
        self.assertIn("set $mod Mod4",session)
        self.assertTrue((self.home/".config"/"tvwcs"/"hotkeys.conf").is_file())
        launcher=(self.home/".local"/"share"/"applications"/"com.tvwcs.ControlPanel.desktop").read_text()
        self.assertIn(f'Exec="{self.dest}/bin/tvwcs" settings',launcher)
        self.assertFalse((self.home/".config"/"i3").exists())   # the usual session is left alone
        self.assertFalse(self.log.exists())                       # nothing installed with apt
        self.assertIn("Run install.sh in a terminal once to add TVWCS's i3 session",self.out)

    # ------------------------------------------------------------------ a new install, on a terminal
    def test_a_new_install_asks_everything_first_then_installs(self):
        self.wm("sway")
        out=self.converse([],{"Choose 1-":"","Go ahead":"y","sudo rule":"n"},TVWCS_PACKAGES="python3 python3-gi")
        self.assertEqual(self.status,0,out)
        self.assertIn(f"Install TVWCS {self.version()} from this package",out)
        self.assertIn("sway is installed.",out)
        self.assertIn("There is no login screen here, so TVWCS's own is installed",out)
        self.assertIn("These packages will be installed:",out)
        self.assertIn("TVWCS's login screen\n      greetd cage",out)
        self.assertIn("gir1.2-gtk-4.0 python3-gi-cairo",out)
        self.assertLess(out.index("Go ahead?"),out.index("Installing:"))   # nothing before the last question
        apt=self.log.read_text(); self.assertIn("apt-get install -y gir1.2-gtk-4.0 python3-gi-cairo sway swayidle swaylock greetd cage",apt)
        self.assertIn("greetd",(self.home/".config"/"tvwcs"/"installed-packages").read_text())
        self.assertTrue((self.home/".config"/"tvwcs"/"sway-session.conf").is_file())
        self.assertIn("Exec=",(self.share/"wayland-sessions"/"tvwcs-sway.desktop").read_text())
        self.assertIn("tvwcs-greeter/greeter",(self.etc/"greetd"/"config.toml").read_text())
        state=json.loads((self.root/"var"/"lib"/"tvwcs-greeter"/"state.json").read_text())
        self.assertEqual(state["users"][os.environ.get("USER") or subprocess.run(["id","-un"],capture_output=True,text=True).stdout.strip()]["session"],"tvwcs-sway")
        self.assertFalse((self.home/".config"/"sway").exists())   # "Not now"
        self.assertIn('choose "TVWCS (sway)" at the login screen',out)
    def test_suggests_sway_when_neither_is_installed_and_offers_both(self):
        out=self.converse([],{"Which should TVWCS use":"","Choose 1-3 [3]":"3","Go ahead":"n"})
        self.assertIn("sway is recommended: it plays video more smoothly. i3 may work better",out)
        self.assertIn("1) sway (recommended)",out); self.assertIn("Nothing was changed.",out)
        self.assertFalse(self.dest.exists())
    def test_declining_at_the_end_changes_nothing(self):
        self.wm("i3")
        out=self.converse([],{"Go ahead":"n"})
        self.assertIn("Nothing was changed.",out); self.assertFalse(self.dest.exists()); self.assertFalse(self.log.exists())
    def test_a_failed_install_undoes_what_it_did(self):
        self.wm("i3"); (self.home/".config"/"i3").mkdir(parents=True); (self.home/".config"/"i3"/"config").write_text("# mine\n")
        out=self.converse([],{"desktop mode?":"y","Go ahead":"y","sudo rule":"n"},APT_FAILS="1")
        self.assertNotEqual(self.status,0); self.assertIn("The installation failed: the packages could not be installed.",out)
        self.assertIn("Undoing the changes made so far",out)
        self.assertFalse(self.dest.exists()); self.assertEqual((self.home/".config"/"i3"/"config").read_text(),"# mine\n")
        self.assertIn("apt-get remove -y",self.log.read_text())
    def test_adds_tvwcs_to_the_usual_session_only_when_asked(self):
        self.wm("i3"); cfg=self.home/".config"/"i3"/"config"; cfg.parent.mkdir(parents=True); cfg.write_text("# mine\n")
        self.converse([],{"desktop mode?":"","Go ahead":"y","sudo rule":"n","login screen":"n"})
        self.assertEqual(cfg.read_text(),"# mine\n")
        self.converse([],{"desktop mode?":"y","Go ahead":"y","sudo rule":"n"})
        text=cfg.read_text(); self.assertTrue(text.rstrip().endswith("include ~/.local/share/tvwcs/tvwcs.conf"),text)
        self.assertTrue((cfg.parent/"config.tvwcs-backup").is_file())
        out=self.converse([],{"Go ahead":"y","sudo rule":"n"})   # already in: not asked again, and not added twice
        self.assertNotIn("desktop mode?",out); self.assertEqual(cfg.read_text().count("tvwcs.conf"),1)
    def test_creates_a_usual_config_with_the_chosen_keys(self):
        self.wm("i3")
        self.converse(["","","2"],{"Choose 1-3 [3]":"1","keyboard layout":"n",
                          "Keyboard layout (":"de nodeadkeys","Go ahead":"y","sudo rule":"n"})
        text=(self.home/".config"/"i3"/"config").read_text()
        self.assertIn("set $mod Mod1",text); self.assertNotIn("WARNING",text); self.assertIn("setxkbmap -layout de -variant nodeadkeys",text)
        self.assertIn("include ~/.local/share/tvwcs/tvwcs.conf",text)
        self.assertIn("set $mod Mod1",(self.home/".config"/"tvwcs"/"i3-session.conf").read_text())
    def test_sway_with_lightdm_offers_five_ways_on(self):
        self.wm("sway"); (self.etc/"X11").mkdir(); (self.etc/"X11"/"default-display-manager").write_text("/usr/sbin/lightdm\n")
        out=self.converse([],{"What should be done":"","Choose 1-5 [1]":"2","Go ahead":"n"})
        for choice in ("Install TVWCS's login screen","Use i3 instead of sway","Install SDDM","install sway anyway","Cancel the installation"):
            self.assertIn(choice,out)
        self.assertIn("TVWCS (i3) session",out); self.assertNotIn("TVWCS (sway) session",out)
        out=self.converse([],{"Choose 1-5 [1]":"5"}); self.assertIn("Nothing was changed.",out)
    def test_another_login_screen_is_only_replaced_on_a_clear_yes(self):
        self.wm("i3"); (self.etc/"X11").mkdir(); (self.etc/"X11"/"default-display-manager").write_text("/usr/sbin/lightdm\n")
        out=self.converse([],{"Use TVWCS's login screen instead?":"","Go ahead":"y","sudo rule":"n"})
        self.assertIn("This computer uses LightDM",out); self.assertFalse((self.etc/"greetd").exists())

    # ------------------------------------------------------------------ versions
    def test_a_standalone_script_offers_the_latest_release_or_another(self):
        alone=Path(self.tmp.name)/"alone"; alone.mkdir(); shutil.copy(SCRIPT,alone/"install.sh")
        self.releases("4.0.0",[("4.1.0",True),("4.0.0",False),("3.6.1",False),("3.6.0",False),("3.5.2",False)])
        self.release("4.0.0"); self.release("4.1.0"); self.wm("i3")
        out=self.converse([],{"Choose 1-3 [1]":"2","Choose 1-4 [1]":"1","Go ahead":"y","sudo rule":"n","login screen":"n"},script=alone/"install.sh")
        self.assertIn("Install TVWCS 4.0.0, the latest release",out)
        self.assertIn("1) 4.1.0, the prerelease",out); self.assertIn("2) 3.6.1, an earlier release",out); self.assertIn("3) 3.6.0, an earlier release",out)
        self.assertNotIn("3.5.2",out); self.assertNotIn("9.9.9",out)
        self.assertEqual(self.status,0,out); self.assertEqual((self.dest/"VERSION").read_text().strip(),"4.1.0")
    def test_piped_to_a_shell_without_a_terminal_it_installs_the_latest(self):
        self.releases("4.0.0",[("4.0.0",False)]); self.release("4.0.0"); self.wm("i3")
        with open(SCRIPT,"rb") as f: p=self.run_install(stdin=f,script=Path("/dev/stdin"))
        self.assertEqual(p.returncode,0,self.out); self.assertEqual((self.dest/"VERSION").read_text().strip(),"4.0.0")
    def test_a_package_offers_itself_first_then_the_latest(self):
        self.releases("9.0.0",[("9.0.0",False)]); self.wm("i3")
        out=self.converse([],{"Choose 1-4 [1]":"4"})
        self.assertIn(f"1) Install TVWCS {self.version()} from this package",out)
        self.assertIn("2) Install TVWCS 9.0.0, the latest release (downloaded)",out); self.assertIn("Nothing was changed.",out)

    # ------------------------------------------------------------------ upgrading
    def installed(self, version="3.6.1"):
        self.run_install(TVWCS_WMS="i3"); (self.dest/"VERSION").write_text(version+"\n")
    def test_an_upgrade_from_3_cleans_up_and_explains_the_sessions(self):
        self.wm("i3"); self.installed()
        cfg=self.home/".config"/"i3"/"config"; cfg.parent.mkdir(parents=True); cfg.write_text("# mine\ninclude ~/.local/share/tvwcs/tvwcs.conf\n")
        (self.home/".config"/"tvwcs"/"setup").write_text("dedicated\n")
        out=self.converse([],{"Choose 1-":"","Go ahead":"y","sudo rule":"n","login screen":"n"})
        self.assertIn(f"Upgrade to TVWCS {self.version()} from this package",out); self.assertIn("Remove TVWCS",out)
        self.assertIn("TVWCS's TV mode is now the \"TVWCS\" session at the login screen",out)
        self.assertIn(f"{cfg} includes TVWCS",out); self.assertIn("cp '",out)
        self.assertFalse((self.home/".config"/"tvwcs"/"setup").exists())
        self.assertEqual(cfg.read_text().count("tvwcs.conf"),1)

    # ------------------------------------------------------------------ removing
    def test_remove_needs_another_login_screen_first(self):
        self.wm("i3"); self.installed(self.version())
        (self.etc/"systemd"/"system").mkdir(parents=True); (self.etc/"systemd"/"system"/"display-manager.service").symlink_to("/lib/systemd/system/greetd.service")
        (self.etc/"greetd").mkdir(); (self.etc/"greetd"/"config.toml").write_text('[default_session]\ncommand = "cage -s -d -- /usr/local/lib/tvwcs-greeter/greeter"\n')
        out=self.converse([],{"Choose 1-3 [1]":"2"})
        self.assertIn("TVWCS's login screen is the only one installed",out); self.assertTrue(self.dest.exists())
        units=self.root/"lib"/"systemd"/"system"; units.mkdir(parents=True); (units/"sddm.service").write_text("")
        out=self.converse([],{"Choose 1-3 [1]":"2","Remove TVWCS now?":"y"})
        self.assertIn("goes back to SDDM",out); self.assertIn("TVWCS is removed.",out)
        self.assertFalse(self.dest.exists()); self.assertTrue((self.home/".config"/"tvwcs").exists())
        self.assertNotIn("tvwcs-greeter",(self.etc/"greetd"/"config.toml").read_text())
    def test_remove_takes_tvwcs_out_of_the_usual_config_and_offers_to_mark_packages(self):
        self.wm("i3"); self.installed(self.version())
        cfg=self.home/".config"/"i3"/"config"; cfg.parent.mkdir(parents=True)
        cfg.write_text("# mine\n\n# TVWCS (desktop mode): added.\ninclude ~/.local/share/tvwcs/tvwcs.conf\n")
        (self.home/".config"/"tvwcs"/"installed-packages").write_text("greetd\nxdotool\n")
        tool(self.bin,"apt-mark",f'[ "$1" = showmanual ] && {{ echo greetd; echo xdotool; exit 0; }}; echo "apt-mark $*" >> "{self.log}"')
        tool(self.bin,"apt-cache",'for a; do p=$a; done; echo "$p"; echo "Reverse Depends:"; [ "$p" = xdotool ] && echo "  some-game"; exit 0')
        out=self.converse([],{"Choose 1-3 [1]":"2","Mark them as removable?":"y","Also delete":"y","Remove TVWCS now?":"y"},
                          TVWCS_PACKAGES="greetd xdotool")
        self.assertIn("won't",out.replace("does not","won't")); self.assertIn("sudo apt autoremove",out)
        self.assertIn("apt-mark auto greetd",self.log.read_text()); self.assertNotIn("xdotool",self.log.read_text())
        self.assertEqual(cfg.read_text().rstrip(),"# mine")
        self.assertFalse((self.home/".config"/"tvwcs").exists())

if __name__=="__main__": unittest.main()
