"""Settings > Features (features.py): what is on, and when a feature's packages may be uninstalled."""
import os, shutil, tempfile, unittest
from types import SimpleNamespace
from unittest import mock

from tvwcs import features as F

def fake_run(installed, simulated="", code=0):
    """A stand-in for subprocess.run: dpkg-query answers from `installed`, apt-get -s remove with `simulated`."""
    def run(argv, **_k):
        if argv[0]=="dpkg-query":
            return SimpleNamespace(stdout="".join(f"{p}\t{'ii ' if p in installed else 'un '}\n" for p in argv[3:]),returncode=0,stderr="")
        if argv[:3]==["apt-get","-s","remove"]: return SimpleNamespace(stdout=simulated,returncode=code,stderr="E: broken" if code else "")
        raise AssertionError(argv)
    return run

class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.which=mock.patch.object(F.shutil,"which",side_effect=lambda n:f"/usr/bin/{n}"); self.which.start()
        self.proc=tempfile.mkdtemp()
    def tearDown(self): self.which.stop()
    def test_everything_is_on_unless_turned_off(self):
        self.assertTrue(F.enabled({},"sound")); self.assertTrue(F.enabled({"features":{}},"sound"))
        self.assertFalse(F.enabled({"features":{"sound":False}},"sound"))
        self.assertFalse(F.page_enabled({"features":{"sound":False}},"sound")); self.assertTrue(F.page_enabled({"features":{"sound":False}},"options"))
        self.assertEqual(F.clean({"sound":False,"nope":False,"bluetooth":True,"terminal":0}),{"sound":False})
        self.assertEqual(F.clean(None),{})
    def test_samba_is_off_until_turned_on(self):
        self.assertFalse(F.enabled({},"samba")); self.assertTrue(F.enabled({"features":{"samba":True}},"samba"))
        self.assertEqual(F.clean({"samba":True,"sound":True}),{"samba":True}); self.assertEqual(F.clean({"samba":False}),{})
        chosen={}; F.choose(chosen,"samba",True); self.assertEqual(chosen,{"samba":True})
        F.choose(chosen,"samba",False); F.choose(chosen,"sound",False); self.assertEqual(chosen,{"sound":False})
        self.assertNotIn("storage",F.BY_KEY); self.assertNotIn("network",F.BY_KEY)
    def test_x11_only_features(self):
        self.assertFalse(F.applies(F.BY_KEY["cursor"],{"SWAYSOCK":"/run/sway"})); self.assertTrue(F.applies(F.BY_KEY["cursor"],{}))
    def test_uninstall_when_nothing_else_needs_it(self):
        bt=F.BY_KEY["bluetooth"]
        packages,why=F.removable(bt,{},fake_run({"bluez"},"Remv bluez [5.66-1]\n"),self.proc)
        self.assertEqual((packages,why),(["bluez"],""))
        self.assertEqual(F.remove_argv(packages),["env","DEBIAN_FRONTEND=noninteractive","apt-get","remove","-y","bluez"])
    def test_no_uninstall_when_other_software_needs_it(self):
        packages,why=F.removable(F.BY_KEY["bluetooth"],{},fake_run({"bluez"},"Remv bluez [5]\nRemv gnome-bluetooth [3]\n"),self.proc)
        self.assertEqual(packages,[]); self.assertIn("gnome-bluetooth",why)
    def test_no_uninstall_of_what_is_not_installed_or_apt_refuses(self):
        self.assertIn("not installed",F.removable(F.BY_KEY["bluetooth"],{},fake_run(set()),self.proc)[1])
        self.assertIn("broken",F.removable(F.BY_KEY["bluetooth"],{},fake_run({"bluez"},code=100),self.proc)[1])
    def test_a_feature_in_use_is_never_uninstalled(self):
        os.makedirs(os.path.join(self.proc,"42"))
        with open(os.path.join(self.proc,"42","comm"),"w") as f: f.write("NetworkManager\n")
        nm=F.Feature("nm","NM","",("network-manager",),(("cmd","nmcli"),),in_use=("NetworkManager",))
        packages,why=F.removable(nm,{},fake_run({"network-manager"},"Remv network-manager [1]\n"),self.proc)
        self.assertEqual(packages,[]); self.assertIn("NetworkManager is running",why)
    def test_packages_of_tvwcs_itself_are_kept(self):
        fake=F.Feature("x","X","",("x11-xserver-utils","extra"),())
        packages,_why=F.removable(fake,{},fake_run({"x11-xserver-utils","extra"},"Remv extra [1]\n"),self.proc)
        self.assertEqual(packages,["extra"])
    def test_package_names_are_checked(self):
        with self.assertRaises(ValueError): F.install_argv(["bluez; rm -rf /"])
        self.assertEqual(F.install_argv(["bluez"])[-1],"bluez")
    def test_unclutter_is_installed_without_its_every_session_autostart(self):
        if not shutil.which("dpkg-query"): self.skipTest("dpkg-query is not installed here")
        class Done: stdout="unclutter-startup\tun \n"
        self.assertEqual(F.install_argv(["unclutter-xfixes"],run=lambda *a,**k:Done())[-2:],["unclutter-xfixes","unclutter-startup-"])
        Done.stdout="unclutter-startup\tii \n"   # installed already (by its owner): left alone
        self.assertEqual(F.install_argv(["unclutter-xfixes"],run=lambda *a,**k:Done())[-1],"unclutter-xfixes")

if __name__=="__main__": unittest.main()
