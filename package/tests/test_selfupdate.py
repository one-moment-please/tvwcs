import tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch

from tvwcs import selfupdate
from tvwcs.selfupdate import Release, UpdateError

def release_json(tag="v2.6.0",names=("TVWCS-2.6.0.zip",)):
    return {"tag_name":tag,"html_url":"https://example/rel","assets":[{"name":n,"browser_download_url":f"https://example/{n}"} for n in names]}

class VersionTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(selfupdate.parse_version("v2.6.0"),(2,6,0)); self.assertEqual(selfupdate.parse_version("2.6.0-beta.3"),(2,6,0))
        with self.assertRaises(UpdateError): selfupdate.parse_version("beta-12")
    def test_newer(self):
        self.assertTrue(selfupdate.is_newer("v2.6.0","2.5.0")); self.assertTrue(selfupdate.is_newer("2.10","2.9.9"))
        self.assertFalse(selfupdate.is_newer("2.5.0","2.5.0")); self.assertFalse(selfupdate.is_newer("2.5","2.5.0")); self.assertFalse(selfupdate.is_newer("2.4.9","2.5.0"))

class ReleaseTests(unittest.TestCase):
    def test_picks_the_release_zip(self):
        r=selfupdate.release_from_json(release_json(names=("notes.txt","TVWCS-2.6.0-beta.1.zip","TVWCS-2.6.0.zip")))
        self.assertEqual((r.version,r.tag,r.zip_url),("2.6.0","v2.6.0","https://example/TVWCS-2.6.0.zip"))
    def test_no_zip_is_an_error(self):
        with self.assertRaises(UpdateError): selfupdate.release_from_json(release_json(names=("notes.txt",)))

class InstallTests(unittest.TestCase):
    def test_install_dir_only_for_installed_layout(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/"tvwcs").mkdir(); (root/"bin").mkdir()
            self.assertIsNone(selfupdate.install_dir(root/"tvwcs"))   # a source checkout has no tvwcs.conf beside the package
            (root/"tvwcs.conf").write_text(""); (root/"bin"/"tvwcs").write_text("")
            self.assertEqual(selfupdate.install_dir(root/"tvwcs"),root.resolve())
    def _zip(self,path,files):
        with zipfile.ZipFile(path,"w") as z:
            for name,text in files.items(): z.writestr(name,text)
    def test_install_runs_the_zips_install_script_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/"src.zip"; dest=Path(d)/"dest"; dest.mkdir(); seen=[]
            self._zip(src,{"tvwcs/install.sh":'echo "$TVWCS_DEST" > "$TVWCS_DEST/ran"; pwd >> "$TVWCS_DEST/ran"\n',"tvwcs/tvwcs/main.py":""})
            def fake_download(_url,target): seen.append(Path(target).parent); Path(target).write_bytes(src.read_bytes())
            with patch.object(selfupdate,"_download",fake_download):
                selfupdate.install_release(Release("2.6.0","v2.6.0","https://example/z.zip",""),dest)
            self.assertEqual((dest/"ran").read_text().splitlines()[0],str(dest))
            self.assertFalse(seen[0].exists())   # the download folder is gone afterwards
    def test_a_zip_that_is_not_tvwcs_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/"src.zip"; self._zip(src,{"other/install.sh":"exit 0\n"})
            with patch.object(selfupdate,"_download",lambda _u,t:Path(t).write_bytes(src.read_bytes())):
                with self.assertRaises(UpdateError): selfupdate.install_release(Release("2.6.0","v2.6.0","x",""),Path(d))
    def test_failing_install_script_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/"src.zip"; self._zip(src,{"tvwcs/install.sh":"echo broken >&2; exit 3\n","tvwcs/tvwcs/main.py":""})
            with patch.object(selfupdate,"_download",lambda _u,t:Path(t).write_bytes(src.read_bytes())):
                with self.assertRaisesRegex(UpdateError,"broken"): selfupdate.install_release(Release("2.6.0","v2.6.0","x",""),Path(d))

if __name__=="__main__": unittest.main()
