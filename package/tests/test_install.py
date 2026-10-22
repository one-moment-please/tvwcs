"""install.sh in a throwaway system: a home folder, /etc and /usr/share under a temporary folder, and stand-ins for
sudo, apt-get and wget. Covers the questions it asks first, what it then installs, the versions it offers, upgrading
from 4.x (its own login screen and its copy in ~/.local/share/tvwcs) and removing TVWCS. Skipped outside the
repository."""
import json, os, pty, select, shutil, subprocess, tempfile, time, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/"install.sh"
SWAY="# Default config for sway\nset $mod Mod4\nbindsym $mod+Return exec $term\n"
OLD_GREETD="""[terminal]
vt = 7

[default_session]
command = "cage -s -d -- /usr/local/lib/tvwcs-greeter/greeter"
user = "_greetd"

[initial_session]
command = "/usr/local/lib/tvwcs-greeter/start-session x11 i3 /usr/local/bin/tvwcs-session i3"
user = "tv"
"""

def tool(folder, name, body):
    p=Path(folder)/name; p.write_text("#!/bin/sh\n"+body+"\n"); p.chmod(0o755); return p

@unittest.skipUnless((ROOT/"package"/"tvwcs").is_dir(),"install.sh is only tested in the repository")
class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); t=Path(self.tmp.name)
        self.root=t/"root"; self.etc=self.root/"etc"; self.home=t/"home user"; self.home.mkdir()   # a space, to test quoting
        (self.etc/"sway").mkdir(parents=True); (self.etc/"sway"/"config").write_text(SWAY); (self.etc/"greetd").mkdir()
        (self.etc/"systemd"/"system").mkdir(parents=True)
        (self.etc/"os-release").write_text("ID=debian\n")
        self.share=self.root/"usr"/"share"; self.share.mkdir(parents=True)
        self.units=self.root/"lib"/"systemd"/"system"; self.units.mkdir(parents=True); (self.units/"greetd.service").write_text("")
        self.lib=t/"lib"; self.lib.mkdir(); (self.lib/"tvwcs").symlink_to(ROOT/"package"/"tvwcs")   # the installed package
        self.bin=t/"fakebin"; self.bin.mkdir(); self.log=t/"log"
        tool(self.bin,"sudo",'exec "$@"')
        tool(self.bin,"apt-get",f'echo "apt-get $*" >> "{self.log}"; exit 0')
        self.downloads=t/"downloads"; self.downloads.mkdir()
        # wget: the file named after the URL's last parts in downloads/ (a/b/c -> a_b_c), else fail
        tool(self.bin,"wget",f'out=$2; url=$3; f=$(echo "$url" | sed "s#^[a-z]*://[^/]*/##; s#[/?=&]#_#g"); [ -f "{self.downloads}/$f" ] || exit 8; cp "{self.downloads}/$f" "$out"')
        self.old=self.home/".local"/"share"/"tvwcs"
        self.sys=t/"sysbin"; self.sys.mkdir(); hidden={"sway","gdm3","gdm","sddm","lightdm","greetd","wget","curl","sudo","doas","apt-get"}
        for d in os.environ["PATH"].split(":"):
            if not os.path.isdir(d): continue
            for e in os.scandir(d):
                if e.name not in hidden and not (self.sys/e.name).exists() and os.access(e.path,os.X_OK): (self.sys/e.name).symlink_to(e.path)
        self.env={"PATH":f"{self.bin}:{self.sys}","HOME":str(self.home),"TVWCS_ETC":str(self.etc),"TVWCS_ROOT":str(self.root),
                  "TVWCS_SHARE":str(self.share),"TVWCS_LIB":str(self.lib),"TVWCS_LOCAL":str(self.root/"usr"/"local"),"TVWCS_RUN":str(t/"run"),
                  "TVWCS_PACKAGES":"","TVWCS_GITHUB":"https://github.test","TVWCS_API":"https://api.test","TVWCS_UNITS":str(self.units),"LANG":"C.UTF-8"}
        (t/"run"/"systemd"/"system").mkdir(parents=True)
        self.pkg=t/"pkg"; self.pkg.mkdir(); shutil.copy(SCRIPT,self.pkg/"install.sh")
        (self.pkg/"tvwcs_5.0.0_all.deb").write_bytes(b"!<arch>\n")
    def tearDown(self): self.tmp.cleanup()
    def apt(self): return self.log.read_text() if self.log.exists() else ""
    def greetd(self): return (self.etc/"greetd"/"config.toml").read_text()
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
    def releases(self, latest, rows):
        """GitHub's release list: rows of (version, prerelease), each with its packages to download."""
        items=[{"url":"x","tag_name":f"v{v}","name":f"TVWCS {v}","draft":False,"prerelease":pre,"body":'not a "tag_name": "v9.9.9"'} for v,pre in rows]
        (self.downloads/"repos_one-moment-please_tvwcs_releases_per_page_30").write_text(json.dumps(items,indent=2))
        (self.downloads/"repos_one-moment-please_tvwcs_releases_latest").write_text(json.dumps({"tag_name":f"v{latest}","prerelease":False}))
        for v,_pre in rows:
            (self.downloads/f"one-moment-please_tvwcs_releases_download_v{v}_tvwcs_{v}_all.deb").write_bytes(b"!<arch>\n")

    def test_help_and_options(self):
        p=self.run_install("--help"); self.assertEqual(p.returncode,0); self.assertIn("--remove",p.stdout); self.assertNotIn("set -eu",p.stdout)
        self.assertEqual(self.run_install("--bogus").returncode,2)
        p=self.run_install("--missing"); self.assertEqual((p.returncode,p.stdout),(0,""))   # what 4.x's updater asks first
    def test_without_a_terminal_it_says_to_run_it_in_one(self):
        p=self.run_install(); self.assertEqual(p.returncode,1); self.assertIn("in a terminal",self.out); self.assertEqual(self.apt(),"")
    def test_a_new_install_without_a_login_screen_sets_up_greetd(self):
        out=self.converse(["y","y"],script=self.pkg/"install.sh")   # (the package here, the only choice) log in automatically; go ahead
        self.assertEqual(self.status,0,out)
        self.assertIn("There is no login screen here",out)
        apt=self.apt()
        self.assertIn("tvwcs_5.0.0_all.deb greetd",apt); self.assertNotIn("logo",out.lower())
        self.assertIn('command = "/usr/bin/tvwcs-session"',self.greetd()); self.assertIn("/usr/sbin/agreety --cmd /usr/bin/tvwcs-session",self.greetd())
        self.assertEqual(os.readlink(self.etc/"systemd"/"system"/"display-manager.service"),"/lib/systemd/system/greetd.service")
    def test_declining_at_the_end_changes_nothing(self):
        out=self.converse(["n","n"],script=self.pkg/"install.sh")
        self.assertIn("Nothing was changed",out); self.assertEqual(self.apt(),""); self.assertFalse((self.etc/"greetd"/"config.toml").exists())
    def test_the_usual_sway_session(self):
        cfg=self.home/".config"/"sway"/"config"; cfg.parent.mkdir(parents=True); cfg.write_text("# mine\n")
        self.use("greetd"); (self.etc/"greetd"/"config.toml").write_text('[default_session]\ncommand = "tuigreet"\nuser = "greeter"\n')
        out=self.converse(["n","y","y"],script=self.pkg/"install.sh")   # no automatic login; desktop mode; go ahead
        self.assertEqual(self.status,0,out)
        self.assertNotIn("greetd",self.apt().split("tvwcs_5.0.0_all.deb")[1])
        self.assertIn("include /usr/share/tvwcs/tvwcs.conf",cfg.read_text()); self.assertEqual(Path(str(cfg)+".tvwcs-backup").read_text(),"# mine\n")
        self.assertIn("tuigreet",self.greetd())
    def test_5_0s_boot_logo_is_removed(self):
        out=self.converse([],{"automatically":"n","Go ahead":"y"},script=self.pkg/"install.sh",TVWCS_PACKAGES="tvwcs-boot-logo")
        self.assertEqual(self.status,0,out)
        self.assertIn("remove the TVWCS logo at startup",out); self.assertIn("purge -y tvwcs-boot-logo",self.apt())
    def use(self, unit):
        link=self.etc/"systemd"/"system"/"display-manager.service"
        if link.is_symlink(): link.unlink()
        link.symlink_to(f"/lib/systemd/system/{unit}.service")
    def test_an_upgrade_from_4_removes_the_old_copy_and_login_screen(self):
        self.old.mkdir(parents=True); (self.old/"VERSION").write_text("4.2.2\n")
        self.use("greetd"); (self.etc/"greetd"/"config.toml").write_text(OLD_GREETD)
        lib=self.root/"usr"/"local"/"lib"/"tvwcs-greeter"; lib.mkdir(parents=True); (lib/"greeter").write_text("")
        sw=self.home/".config"/"sway"/"config"; sw.parent.mkdir(parents=True); sw.write_text("include ~/.local/share/tvwcs/tvwcs.conf\n")
        i3=self.home/".config"/"i3"/"config"; i3.parent.mkdir(parents=True); i3.write_text("# i3\ninclude ~/.local/share/tvwcs/tvwcs.conf\n")
        prof=self.home/".profile"; prof.write_text("# mine\n# >>> TVWCS: start the window manager after the automatic login (added by install.sh; delete to undo) >>>\nexec sway\n# <<< TVWCS <<<\n")
        apps=self.home/".local"/"share"/"applications"; apps.mkdir(parents=True); (apps/"com.tvwcs.ControlPanel.desktop").write_text("")
        out=self.converse(["y"],script=self.pkg/"install.sh")   # go ahead
        self.assertEqual(self.status,0,out)
        self.assertIn("TVWCS 4.2.2 is installed",out); self.assertIn("tv is still logged in automatically",out)
        self.assertIn('command = "/usr/bin/tvwcs-session"',self.greetd()); self.assertIn('user = "tv"',self.greetd()); self.assertNotIn("tvwcs-greeter",self.greetd())
        self.assertFalse(lib.exists()); self.assertFalse(self.old.exists()); self.assertFalse((apps/"com.tvwcs.ControlPanel.desktop").exists())
        self.assertEqual(sw.read_text(),"include /usr/share/tvwcs/tvwcs.conf\n"); self.assertEqual(i3.read_text(),"# i3\n")
        self.assertEqual(prof.read_text(),"# mine\n")
    def test_a_standalone_script_downloads_the_release(self):
        self.releases("4.2.2",[("5.1.0",True),("5.0.0",True),("4.2.2",False)])
        out=self.converse(["","n","y"])   # the first offer: the newest prerelease (no 5.x is the latest yet)
        self.assertEqual(self.status,0,out)
        self.assertIn("TVWCS 5.1.0, a prerelease",out); self.assertNotIn("4.2.2",out)
        self.assertIn("tvwcs_5.1.0_all.deb",self.apt())
    def test_the_package_here_is_not_offered_twice(self):
        self.releases("",[("5.0.1",True),("5.0.0",True)])
        out=self.converse(["1","n","y"],script=self.pkg/"install.sh")   # the package here; no automatic login; go ahead
        self.assertEqual(self.status,0,out)
        self.assertIn("TVWCS 5.0.1, a prerelease",out); self.assertNotIn("TVWCS 5.0.0, a prerelease",out)
    def test_on_ubuntu_it_offers_to_remove_its_extras_one_by_one(self):
        (self.etc/"os-release").write_text("ID=ubuntu\nID_LIKE=debian\n")
        out=self.converse([],{"automatically":"n","Remove Snap":"y","Remove cloud-init":"","Go ahead":"y"},
                          script=self.pkg/"install.sh",TVWCS_PACKAGES="snapd cloud-init")
        self.assertEqual(self.status,0,out)
        self.assertIn("== Ubuntu extras",out); self.assertNotIn("Ubuntu Pro client",out)   # not installed: not offered
        self.assertIn("  remove Snap (snapd)\n",out); self.assertLess(out.index("Go ahead?"),out.index("Removing Snap (snapd)..."))
    def test_extras_are_only_offered_on_ubuntu(self):
        out=self.converse([],{"automatically":"n","Go ahead":"y"},script=self.pkg/"install.sh",TVWCS_PACKAGES="snapd cloud-init")
        self.assertEqual(self.status,0,out); self.assertNotIn("Ubuntu extras",out)
    def test_remove(self):
        self.use("greetd"); (self.etc/"greetd"/"config.toml").write_text('[default_session]\ncommand = "agreety --cmd /usr/bin/tvwcs-session"\nuser = "_greetd"\n')
        cfg=self.home/".config"/"sway"/"config"; cfg.parent.mkdir(parents=True)
        cfg.write_text("# mine\n\n# TVWCS (desktop mode): its hotkeys, window rules and autostart. Added by TVWCS's install.sh.\ninclude /usr/share/tvwcs/tvwcs.conf\n")
        pid,fd=pty.fork()
        if pid==0: os.execvpe("sh",["sh",str(SCRIPT),"--remove"],self.env)
        os.write(fd,b"y\nn\n"); out=b""
        while True:
            try: chunk=os.read(fd,4096)
            except OSError: break
            if not chunk: break
            out+=chunk
        os.waitpid(pid,0)
        self.assertIn("purge -y tvwcs\n",self.apt(),out)
        self.assertNotIn("tvwcs",cfg.read_text().replace("# mine","")); self.assertIn('"/usr/sbin/agreety --cmd /bin/sh"',self.greetd())

if __name__=="__main__": unittest.main()
