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
    def test_prereleases_only_when_asked_and_newer(self):
        listing=[dict(release_json("v2.10.3",("TVWCS-2.10.3.zip",)),prerelease=True),dict(release_json("v2.10.4"),draft=True),
                 release_json("beta-12",("TVWCS-2.5.0-beta.12.zip",)),release_json("v2.10.2",("TVWCS-2.10.2.zip",)),
                 dict(release_json("v2.10.9",("notes.txt",)),prerelease=True)]
        newest=selfupdate.newest_release(listing)
        self.assertEqual((newest.version,newest.prerelease),("2.10.3",True))   # not the draft, the beta tag or the one without a zip
        self.assertIsNone(selfupdate.newest_release([])); self.assertIsNone(selfupdate.newest_release({"message":"rate limited"}))
        answers={selfupdate.LATEST_URL:release_json("v2.10.2",("TVWCS-2.10.2.zip",)),selfupdate.RELEASES_URL:listing}
        with patch.object(selfupdate,"_get_json",answers.get):
            self.assertEqual(selfupdate.latest_release().version,"2.10.2")
            self.assertEqual(selfupdate.latest_release(prereleases=True).version,"2.10.3")
            answers[selfupdate.RELEASES_URL]=[dict(release_json("v2.10.1",("TVWCS-2.10.1.zip",)),prerelease=True)]
            self.assertEqual(selfupdate.latest_release(prereleases=True).version,"2.10.2")   # an older prerelease is not offered
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
    def test_an_install_in_the_old_location_updates_into_the_new_one(self):
        with tempfile.TemporaryDirectory() as d, patch.dict("os.environ",{"XDG_CONFIG_HOME":f"{d}/cfg","XDG_DATA_HOME":f"{d}/data"}):
            self.assertEqual(selfupdate.update_target(Path(d)/"cfg"/"i3"/"tvwcs"),Path(d)/"data"/"tvwcs")
            self.assertEqual(selfupdate.update_target(Path(d)/"opt"),Path(d)/"opt"); self.assertIsNone(selfupdate.update_target(None))
    def test_migrate_lets_install_sh_move_the_old_copy(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/"src.zip"; dest=Path(d)/"dest"; dest.mkdir()
            self._zip(src,{"tvwcs/install.sh":'echo "${TVWCS_MIGRATE:-no}" > "$TVWCS_DEST/migrate"\n',"tvwcs/tvwcs/main.py":""})
            with patch.object(selfupdate,"_download",lambda _u,t:Path(t).write_bytes(src.read_bytes())):
                selfupdate.install_release(Release("2.7.0","v2.7.0","x",""),dest)
                self.assertEqual((dest/"migrate").read_text().strip(),"no")
                selfupdate.install_release(Release("2.7.0","v2.7.0","x",""),dest,migrate=True)
                self.assertEqual((dest/"migrate").read_text().strip(),"1")
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

    def test_missing_packages_are_asked_of_the_new_release_before_installing(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/"src.zip"; dest=Path(d)/"dest"; dest.mkdir()
            script='[ "$1" = --missing ] && { printf "need\\tudisks2\\tSettings: storage\\n"; exit 0; }\necho installed > "$TVWCS_DEST/ran"\n'
            self._zip(src,{"tvwcs/install.sh":script,"tvwcs/tvwcs/main.py":""})
            with patch.object(selfupdate,"_download",lambda _u,t:Path(t).write_bytes(src.read_bytes())):
                folder=selfupdate.download_release(Release("3.1.0","v3.1.0","x",""))
            self.assertEqual(selfupdate.missing_packages(folder),[("udisks2","Settings: storage")])
            self.assertFalse((dest/"ran").exists())   # asking installs nothing
            selfupdate.install_downloaded(folder,dest); self.assertTrue((dest/"ran").exists())
            selfupdate.discard(folder); self.assertFalse(folder.exists())
    def test_an_older_release_is_not_asked(self):
        # Before 3.1 install.sh had no --missing: running it with that would install, so it is not run at all.
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/"src.zip"
            self._zip(src,{"tvwcs/install.sh":'touch "$(dirname "$0")/../ran"\n',"tvwcs/tvwcs/main.py":""})
            with patch.object(selfupdate,"_download",lambda _u,t:Path(t).write_bytes(src.read_bytes())):
                folder=selfupdate.download_release(Release("3.0.3","v3.0.3","x",""))
            self.assertEqual(selfupdate.missing_packages(folder),[]); self.assertFalse((folder/"unpacked"/"ran").exists())
            selfupdate.discard(folder)
    def test_a_bad_download_leaves_nothing_behind(self):
        made=[]
        real=tempfile.mkdtemp
        def mkdtemp(**kw): made.append(real(**kw)); return made[-1]
        with patch.object(selfupdate,"_download",lambda _u,t:Path(t).write_bytes(b"not a zip")), patch.object(selfupdate.tempfile,"mkdtemp",mkdtemp):
            with self.assertRaises(UpdateError): selfupdate.download_release(Release("3.1.0","v3.1.0","x",""))
        self.assertFalse(Path(made[0]).exists())
    def test_parse_missing_and_the_apt_command(self):
        self.assertEqual(selfupdate.parse_missing("need\tudisks2\tstorage\nnoise\nneed\t\tx\n"),[("udisks2","storage")])
        argv=selfupdate.install_packages_argv(["udisks2","xdg-desktop-portal xdg-desktop-portal-gtk"])
        self.assertEqual(argv[-3:],["udisks2","xdg-desktop-portal","xdg-desktop-portal-gtk"]); self.assertEqual(argv[:2],["env","DEBIAN_FRONTEND=noninteractive"])
        with self.assertRaises(ValueError): selfupdate.install_packages_argv(["evil; rm -rf /"])
        with self.assertRaises(ValueError): selfupdate.install_packages_argv([])

if __name__=="__main__": unittest.main()
