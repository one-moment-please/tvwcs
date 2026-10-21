"""features.py: the software each Settings page needs, and how it is installed."""
import shutil, tempfile, unittest
from unittest import mock

from tvwcs import features as F

class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.which=mock.patch.object(F.shutil,"which",side_effect=lambda n:f"/usr/bin/{n}"); self.which.start()
        self.proc=tempfile.mkdtemp()
    def tearDown(self): self.which.stop()
    def test_each_page_knows_the_software_it_needs(self):
        self.assertEqual(F.PAGE_FEATURE["sound"],"sound"); self.assertEqual(F.PAGE_FEATURE["apps"],"apps")
        self.assertNotIn("storage",F.BY_KEY); self.assertNotIn("network",F.BY_KEY)
        self.assertFalse(hasattr(F,"enabled"))   # 4.0: no on/off switch, what is installed is used
    def test_x11_only_features(self):
        self.assertFalse(F.applies(F.BY_KEY["cursor"],{"SWAYSOCK":"/run/sway"})); self.assertTrue(F.applies(F.BY_KEY["cursor"],{}))
    def test_package_names_are_checked(self):
        with self.assertRaises(ValueError): F.install_argv(["bluez; rm -rf /"])
        self.assertEqual(F.install_argv(["bluez"])[-1],"bluez")
    def test_unclutter_is_installed_without_its_every_session_autostart(self):
        if not shutil.which("dpkg-query"): self.skipTest("dpkg-query is not installed here")
        class Done: stdout="unclutter-startup\tun \n"
        self.assertEqual(F.install_argv(["unclutter-xfixes"],run=lambda *a,**k:Done())[-2:],["unclutter-xfixes","unclutter-startup-"])
        Done.stdout="unclutter-startup\tii \n"   # installed already (by its owner): left alone
        self.assertEqual(F.install_argv(["unclutter-xfixes"],run=lambda *a,**k:Done())[-1],"unclutter-xfixes")
    def test_the_screen_saver_on_sway_also_needs_gtk4_layer_shell(self):
        self.assertEqual(F.screensaver({}).packages,("python3-gi-cairo",))
        self.assertEqual(F.screensaver({"SWAYSOCK":"/run/sway"}).packages,("python3-gi-cairo","gir1.2-gtk4layershell-1.0"))
        self.assertFalse(F.applies(F.BY_KEY["sway_saver"],{})); self.assertTrue(F.applies(F.BY_KEY["sway_saver"],{"SWAYSOCK":"/run/sway"}))
    def test_removing_a_feature_names_what_goes_with_it(self):
        self.assertEqual(F.remove_argv(["gvfs-backends"])[-3:],["remove","-y","gvfs-backends"])
        with self.assertRaises(ValueError): F.remove_argv(["gvfs-backends; reboot"])
        sim="Reading package lists...\nThe following packages will be REMOVED:\n  gvfs-backends nautilus\nRemv nautilus [1:43.2-1]\nRemv gvfs-backends [1.50.3-1]\n"
        self.assertEqual(F.parse_removals(sim),["nautilus","gvfs-backends"])
        class Done: stdout=sim
        self.assertEqual(F.removals(["gvfs-backends"],run=lambda *a,**k:Done()),["gvfs-backends","nautilus"])

if __name__=="__main__": unittest.main()
