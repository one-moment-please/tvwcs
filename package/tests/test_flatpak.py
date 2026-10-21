"""The Settings app's Apps page backend: Flathub's appstream catalog, flatpak's remotes and installed apps, parsed
from saved samples. No flatpak or network needed."""
import gzip, io, os, tempfile, unittest
from pathlib import Path

from tvwcs import control_flatpak as fp

APPSTREAM="""<?xml version="1.0" encoding="UTF-8"?>
<components version="0.8" origin="flathub">
  <component type="desktop">
    <id>org.videolan.VLC.desktop</id>
    <name>VLC</name>
    <name xml:lang="de">VLC Player</name>
    <summary>VLC media player, the open-source multimedia framework</summary>
    <summary xml:lang="fr">Lecteur multimédia</summary>
    <description>
      <p>VLC is a free and open source cross-platform <em>multimedia</em> player.</p>
      <p xml:lang="de">VLC ist frei.</p>
      <ul><li>Plays everything</li><li>Runs everywhere</li></ul>
    </description>
    <icon type="remote" width="128" height="128">https://dl.flathub.org/media/vlc.png</icon>
    <icon type="cached" width="64" height="64">org.videolan.VLC.png</icon>
    <icon type="cached" width="128" height="128">org.videolan.VLC.png</icon>
    <icon type="cached" width="128" height="128" scale="2">org.videolan.VLC.png</icon>
    <categories><category>AudioVideo</category><category>Player</category></categories>
    <keywords><keyword>dvd</keyword><keyword xml:lang="de">Abspieler</keyword></keywords>
    <developer_name>VideoLAN</developer_name>
    <project_license>GPL-2.0+</project_license>
    <bundle type="flatpak" runtime="org.kde.Platform/x86_64/5.15-23.08">app/org.videolan.VLC/x86_64/stable</bundle>
    <releases><release version="3.0.21" timestamp="1718000000"/><release version="3.0.20"/></releases>
    <custom><value key="flathub::verification::verified">true</value></custom>
  </component>
  <component type="desktop-application">
    <id>tv.kodi.Kodi</id>
    <name>Kodi</name>
    <summary>Ultimate entertainment center</summary>
    <icon type="cached" width="64" height="64">tv.kodi.Kodi.png</icon>
    <categories><category>AudioVideo</category><category>TV</category></categories>
    <developer id="tv.kodi"><name>Team Kodi</name></developer>
    <bundle type="flatpak">app/tv.kodi.Kodi/x86_64/stable</bundle>
  </component>
  <component type="desktop">
    <id>com.example.VideoTrimmer</id>
    <name>Video Trimmer</name>
    <summary>Trim videos quickly</summary>
    <categories><category>AudioVideo</category><category>Video</category></categories>
    <bundle type="flatpak">app/com.example.VideoTrimmer/x86_64/stable</bundle>
  </component>
  <component type="desktop">
    <id>org.supertuxproject.SuperTux</id>
    <name>SuperTux</name>
    <summary>A jump-and-run game starring Tux the Penguin</summary>
    <categories><category>Game</category><category>ArcadeGame</category></categories>
    <bundle type="flatpak">app/org.supertuxproject.SuperTux/x86_64/stable</bundle>
  </component>
  <component type="runtime">
    <id>org.kde.Platform</id>
    <name>KDE Application Platform</name>
    <bundle type="flatpak">runtime/org.kde.Platform/x86_64/5.15-23.08</bundle>
  </component>
  <component type="addon">
    <id>org.videolan.VLC.Plugin.bdj</id>
    <name>BD-J plugin</name>
    <bundle type="flatpak">runtime/org.videolan.VLC.Plugin.bdj/x86_64/3-23.08</bundle>
  </component>
  <component type="desktop">
    <id>com.example.NoBundle</id>
    <name>Nothing to install</name>
  </component>
</components>
"""

class AppstreamTests(unittest.TestCase):
    def apps(self, icons="/icons"):
        return {a.id:a for a in fp.parse_appstream(io.BytesIO(APPSTREAM.encode()),icons)}

    def test_keeps_only_apps_by_their_flatpak_id(self):
        self.assertEqual(set(self.apps()),{"org.videolan.VLC","tv.kodi.Kodi","com.example.VideoTrimmer","org.supertuxproject.SuperTux"})

    def test_reads_untranslated_fields(self):
        vlc=self.apps()["org.videolan.VLC"]
        self.assertEqual((vlc.name,vlc.summary,vlc.developer,vlc.license,vlc.version),
                         ("VLC","VLC media player, the open-source multimedia framework","VideoLAN","GPL-2.0+","3.0.21"))
        self.assertEqual(vlc.categories,("AudioVideo","Player")); self.assertEqual(vlc.keywords,("dvd",))
        self.assertTrue(vlc.verified)
        self.assertEqual(vlc.description,"VLC is a free and open source cross-platform multimedia player.\n\n• Plays everything\n• Runs everywhere")

    def test_developer_element_and_icons(self):
        apps=self.apps()
        self.assertEqual(apps["tv.kodi.Kodi"].developer,"Team Kodi")
        self.assertEqual(apps["org.videolan.VLC"].icon,"/icons/128x128/org.videolan.VLC.png")
        self.assertEqual(apps["tv.kodi.Kodi"].icon,"/icons/64x64/tv.kodi.Kodi.png")
        self.assertEqual(apps["org.supertuxproject.SuperTux"].icon,"")
        self.assertFalse(apps["tv.kodi.Kodi"].verified)

    def test_reads_gzipped_files_once_per_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"appstream.xml.gz"; path.write_bytes(gzip.compress(APPSTREAM.encode()))
            first=fp.load_catalog(path,Path(tmp)/"icons"); self.assertEqual(len(first),4)
            self.assertIs(fp.load_catalog(path,Path(tmp)/"icons"),first)
            os.utime(path,(1,1)); self.assertIsNot(fp.load_catalog(path,Path(tmp)/"icons"),first)
            self.assertIsNone(fp.load_catalog(Path(tmp)/"missing.xml",None))

    def test_appstream_file_prefers_gz_in_the_user_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)/"flatpak/appstream/flathub/x86_64/active"; base.mkdir(parents=True)
            self.assertEqual(fp.appstream_file("user","x86_64",{"XDG_DATA_HOME":tmp}),(None,None))
            (base/"appstream.xml").write_text(APPSTREAM); (base/"appstream.xml.gz").write_bytes(b"")
            self.assertEqual(fp.appstream_file("user","x86_64",{"XDG_DATA_HOME":tmp}),(base/"appstream.xml.gz",base/"icons"))

class CatalogTests(unittest.TestCase):
    def setUp(self): self.catalog=fp.Catalog(fp.parse_appstream(io.BytesIO(APPSTREAM.encode())))

    def test_featured_keeps_the_list_order_and_skips_missing(self):
        self.assertEqual([a.id for a in self.catalog.featured()],["tv.kodi.Kodi","org.videolan.VLC"])

    def test_category_puts_featured_then_verified_first(self):
        self.assertEqual([a.name for a in self.catalog.category("video")],["Kodi","VLC","Video Trimmer"])
        self.assertEqual([a.name for a in self.catalog.category("games")],["SuperTux"])
        self.assertEqual(self.catalog.category("office"),[])

    def test_search_ranks_names_first_and_needs_every_word(self):
        self.assertEqual([a.name for a in self.catalog.search("v")][:2],["VLC","Video Trimmer"])
        self.assertEqual([a.name for a in self.catalog.search("video")],["Video Trimmer","VLC"])   # VLC by its id (videolan)
        self.assertEqual([a.name for a in self.catalog.search("dvd")],["VLC"])         # a keyword
        self.assertEqual([a.name for a in self.catalog.search("tux game")],["SuperTux"])
        self.assertEqual([a.name for a in self.catalog.search("TEAM kodi")],["Kodi"])  # the developer, any case
        self.assertEqual(self.catalog.search("   "),[])

class FlatpakCommandTests(unittest.TestCase):
    def test_remotes(self):
        self.assertEqual(fp.parse_remotes("flathub\tsystem\nfedora\tsystem,oci\nold\tuser,disabled\n"),
                         {"flathub":{"system"},"fedora":{"system"}})
        self.assertEqual(fp.parse_remotes("Name\tOptions\nflathub\tuser\nflathub\tsystem\n"),{"flathub":{"user","system"}})

    def test_installed(self):
        apps=fp.parse_installed("org.videolan.VLC\tVLC\t3.0.21\tuser\ntv.kodi.Kodi\tKodi\t21.1\tsystem\n\nbroken\n")
        self.assertEqual(apps,[fp.Installed("org.videolan.VLC","VLC","3.0.21","user"),fp.Installed("tv.kodi.Kodi","Kodi","21.1","system")])

    def test_commands(self):
        self.assertEqual(fp.install_argv("tv.kodi.Kodi"),["flatpak","install","--user","-y","--noninteractive","flathub","tv.kodi.Kodi"])
        self.assertEqual(fp.uninstall_argv(fp.Installed("a.b.C","C","","system")),(["flatpak","uninstall","--system","-y","--noninteractive","a.b.C"],True))
        self.assertEqual(fp.uninstall_argv(fp.Installed("a.b.C","C"))[1],False)
        self.assertEqual(fp.setup_argv()[0][:4],["flatpak","remote-add","--user","--if-not-exists"])

class RepositoryTests(unittest.TestCase):
    def test_every_repository_is_listed_with_its_state(self):
        from tvwcs import control_flatpak as fp
        text="flathub\tuser\thttps://dl.flathub.org/repo/\nbeta\tsystem,disabled\thttps://dl.flathub.org/beta-repo/\n"
        self.assertEqual(fp.parse_remote_list(text),[fp.Remote("flathub","user",True,"https://dl.flathub.org/repo/"),
                                                     fp.Remote("beta","system",False,"https://dl.flathub.org/beta-repo/")])
        self.assertEqual(fp.remote_name("https://dl.flathub.org/beta-repo/Flathub-Beta.flatpakrepo"),"flathub-beta")
        self.assertEqual(fp.enable_remote_argv(fp.Remote("beta","system",False),True),(["flatpak","remote-modify","--system","--enable","beta"],True))
        steps=fp.uninstall_all_steps([fp.Installed("a","A","1","user")]); self.assertEqual(len(steps),1)
        steps=fp.uninstall_all_steps([fp.Installed("a","A","1","system")]); self.assertEqual([root for _a,root in steps],[False,True])

if __name__=="__main__": unittest.main()
