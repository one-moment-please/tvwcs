"""Apps for Settings: browsing, installing and removing Flatpak apps from Flathub. No GTK dependency.

The catalog is the Flathub appstream file that flatpak itself downloads (with the remote's cached icons beside it),
so nothing here talks to the network: `flatpak update --appstream` fetches a fresh one. Apps are installed for this
user (`flatpak install --user`), which needs no password; an app someone installed system-wide is removed as root."""
from __future__ import annotations
import gzip, os, platform, xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from tvwcs.control_cmd import have, run

REMOTE="flathub"
FLATHUB_URL="https://dl.flathub.org/repo/flathub.flatpakrepo"
SYSTEM_DIR=Path("/var/lib/flatpak")
_LANG="{http://www.w3.org/XML/1998/namespace}lang"

# Apps that suit a TV, shown first ("Featured"); ids that are not in the catalog are skipped.
FEATURED=("tv.kodi.Kodi","org.videolan.VLC","org.jellyfin.JellyfinDesktop","com.github.iwalton3.jellyfin-media-player","tv.plex.PlexHTPC","com.valvesoftware.Steam",
          "com.moonlight_stream.Moonlight","com.spotify.Client","io.freetubeapp.FreeTube","com.stremio.Stremio","org.libretro.RetroArch",
          "io.mpv.Mpv","org.mozilla.firefox","com.google.Chrome","org.chromium.Chromium","net.lutris.Lutris","com.heroicgameslauncher.hgl",
          "org.DolphinEmu.dolphin-emu","io.github.hmlendea.geforcenow-electron","com.obsproject.Studio","org.gnome.Rhythmbox3")

# (key, label, freedesktop categories); "featured" is FEATURED.
CATEGORIES=(("featured","Featured",frozenset()),
            ("video","Video & music",frozenset({"AudioVideo","Audio","Video","Player","Music","TV","Recorder"})),
            ("games","Games",frozenset({"Game","Emulator"})),
            ("internet","Internet",frozenset({"Network","WebBrowser","Chat","InstantMessaging","Email","P2P"})),
            ("graphics","Graphics & photos",frozenset({"Graphics","Photography"})),
            ("office","Office & education",frozenset({"Office","Education","Science"})),
            ("utilities","Utilities",frozenset({"Utility","System","Settings","Development","FileManager"})))
CATEGORY_LABELS={k:label for k,label,_ in CATEGORIES}

INSTALL_FLATPAK={"apt-get":["apt-get","install","-y","flatpak"],"dnf":["dnf","install","-y","flatpak"],
                 "pacman":["pacman","-S","--needed","--noconfirm","flatpak"],"zypper":["zypper","--non-interactive","install","flatpak"],
                 "xbps-install":["xbps-install","-y","flatpak"],"apk":["apk","add","flatpak"]}

@dataclass(frozen=True)
class App:
    id: str
    name: str
    summary: str = ""
    description: str = ""
    developer: str = ""
    categories: tuple = ()
    keywords: tuple = ()
    icon: str = ""          # a cached icon file, when the catalog has one
    license: str = ""
    version: str = ""
    verified: bool = False

@dataclass(frozen=True)
class Installed:
    id: str
    name: str
    version: str = ""
    installation: str = "user"     # "user" or "system"

# ---------------------------------------------------------------------- parsing (pure)
def parse_remotes(text):
    """`flatpak remotes --columns=name,options`: 'flathub\\tsystem' -> {"flathub": {"system"}}. A disabled remote is left out."""
    found={}
    for line in text.splitlines():
        cols=line.split("\t") if "\t" in line else line.split()
        if not cols or not cols[0].strip() or cols[0].strip()=="Name": continue
        options={o.strip() for o in (cols[1] if len(cols)>1 else "").split(",") if o.strip()}
        if "disabled" in options: continue
        found.setdefault(cols[0].strip(),set()).update(options & {"user","system"} or {"system"})
    return found

def parse_installed(text):
    """`flatpak list --app --columns=application,name,version,installation` (tab separated)."""
    found=[]
    for line in text.splitlines():
        cols=[c.strip() for c in line.split("\t")]
        if len(cols)<2 or "." not in cols[0] or cols[0]=="Application ID": continue
        where=cols[3] if len(cols)>3 and cols[3] in ("user","system") else "system"
        found.append(Installed(cols[0],cols[1] or cols[0],cols[2] if len(cols)>2 else "",where))
    return found

def _text(elem, tag):
    """The untranslated text of a child element (the one without xml:lang)."""
    for child in elem.findall(tag):
        if child.get(_LANG) is None and child.text: return " ".join(child.text.split())
    return ""

def _description(elem):
    """<description>'s paragraphs and list items as plain text."""
    d=next((c for c in elem.findall("description") if c.get(_LANG) is None),None)
    if d is None: return ""
    parts=[]
    for child in d:
        if child.get(_LANG) is not None: continue
        if child.tag=="p":
            text=" ".join("".join(child.itertext()).split())
            if text: parts.append(text)
        elif child.tag in ("ul","ol"):
            items=["• "+" ".join("".join(li.itertext()).split()) for li in child if li.tag=="li" and li.get(_LANG) is None]
            if items: parts.append("\n".join(items))
    return "\n\n".join(parts)

def _icon(elem, icons_dir):
    cached={}
    for icon in elem.findall("icon"):
        if icon.get("type")=="cached" and icon.text and icon.get("width","").isdigit() and icon.get("scale","1")=="1":
            cached[int(icon.get("width"))]=icon.text.strip()
    if not cached or icons_dir is None: return ""
    size=next((s for s in (128,64) if s in cached),max(cached))
    return str(Path(icons_dir)/f"{size}x{size}"/cached[size])

def _component(elem, icons_dir):
    if elem.get("type") not in ("desktop","desktop-application"): return None
    bundle=next((b.text.strip() for b in elem.findall("bundle") if b.get("type")=="flatpak" and b.text),"")
    if not bundle.startswith("app/"): return None   # runtimes, extensions
    app_id=bundle.split("/")[1]
    name=_text(elem,"name")
    if not app_id or not name: return None
    developer=_text(elem,"developer_name")
    if not developer:
        dev=elem.find("developer")
        if dev is not None: developer=_text(dev,"name")
    cats=elem.find("categories"); words=elem.find("keywords"); releases=elem.find("releases")
    release=releases.find("release") if releases is not None else None
    verified=any(v.get("key")=="flathub::verification::verified" and (v.text or "").strip()=="true" for v in elem.iter("value"))
    return App(app_id,name,_text(elem,"summary"),_description(elem),developer,
               tuple(c.text.strip() for c in cats.findall("category") if c.text) if cats is not None else (),
               tuple(k.text.strip() for k in words.findall("keyword") if k.text and k.get(_LANG) is None) if words is not None else (),
               _icon(elem,icons_dir),_text(elem,"project_license"),release.get("version","") if release is not None else "",verified)

def parse_appstream(source, icons_dir=None):
    """Flathub's appstream XML (a path or a file object, gzipped or not) -> [App], read one component at a time."""
    if isinstance(source,(str,Path)):
        opener=gzip.open if str(source).endswith(".gz") else open
        with opener(source,"rb") as f: return parse_appstream(f,icons_dir)
    apps={}
    for _event,elem in ET.iterparse(source,events=("end",)):
        if elem.tag!="component": continue
        app=_component(elem,icons_dir)
        if app is not None: apps[app.id]=app
        elem.clear()
    return list(apps.values())

# ---------------------------------------------------------------------- the catalog
class Catalog:
    def __init__(self, apps, updated=None):
        self.apps=sorted(apps,key=lambda a:a.name.casefold()); self.by_id={a.id:a for a in self.apps}; self.updated=updated
    def __len__(self): return len(self.apps)
    def __eq__(self, other): return isinstance(other,Catalog) and self.updated==other.updated and len(self)==len(other)
    def featured(self): return [self.by_id[i] for i in FEATURED if i in self.by_id]
    def category(self, key):
        if key=="featured": return self.featured()
        wanted=next((c for k,_l,c in CATEGORIES if k==key),frozenset())
        first={i:n for n,i in enumerate(FEATURED)}
        found=[a for a in self.apps if wanted.intersection(a.categories)]
        return sorted(found,key=lambda a:(first.get(a.id,len(first)),not a.verified,a.name.casefold()))
    def search(self, query):
        """Apps matching every word of the query, best first: the name itself, then names that start with it, then
        names with a word that starts with it, then the rest (summary, keywords, developer, id)."""
        words=query.casefold().split()
        if not words: return []
        q=" ".join(words); scored=[]
        for a in self.apps:
            name=a.name.casefold(); hay=" ".join((name,a.summary.casefold(),a.id.casefold(),a.developer.casefold(),*(k.casefold() for k in a.keywords)))
            if not all(w in hay for w in words): continue
            if name==q: score=0
            elif name.startswith(q): score=1
            elif any(part.startswith(words[0]) for part in name.split()): score=2
            elif q in name: score=3
            else: score=4
            scored.append((score,not a.verified,name,a))
        return [s[-1] for s in sorted(scored,key=lambda s:s[:3])]

_cache={}
def load_catalog(path, icons_dir):
    """The catalog in `path`, parsed once per version of the file."""
    try: mtime=os.stat(path).st_mtime
    except OSError: return None
    key=(str(path),mtime)
    if key not in _cache:
        _cache.clear(); _cache[key]=Catalog(parse_appstream(path,icons_dir),mtime)
    return _cache[key]

# ---------------------------------------------------------------------- where flatpak keeps things
def user_dir(env=None):
    env=os.environ if env is None else env
    return Path(env.get("XDG_DATA_HOME") or Path.home()/".local/share")/"flatpak"

def default_arch():
    r=run(["flatpak","--default-arch"],timeout=10)
    if r.ok and r.out.strip(): return r.out.strip()
    return {"amd64":"x86_64","arm64":"aarch64"}.get(platform.machine().lower(),platform.machine())

def appstream_file(installation, arch, env=None):
    """Flatpak's copy of Flathub's catalog for one installation, and its icons folder; (None, None) when there is none."""
    base=(user_dir(env) if installation=="user" else SYSTEM_DIR)/"appstream"/REMOTE/arch/"active"
    for name in ("appstream.xml.gz","appstream.xml"):
        if (base/name).is_file(): return base/name,base/"icons"
    return None,None

# ---------------------------------------------------------------------- commands
def setup_argv():
    """Adding Flathub for this user and downloading its catalog: two steps, neither needs root."""
    return [["flatpak","remote-add","--user","--if-not-exists",REMOTE,FLATHUB_URL],
            ["flatpak","update","--user","--appstream","--noninteractive",REMOTE]]

def install_argv(app_id): return ["flatpak","install","--user","-y","--noninteractive",REMOTE,app_id]
def uninstall_argv(app):
    """(argv, needs root): an app installed for this user is removed by them; one installed system-wide by root."""
    return ["flatpak","uninstall",f"--{app.installation}","-y","--noninteractive",app.id],app.installation=="system"
def run_argv(app_id): return ["flatpak","run",app_id]

def install_flatpak_argv():
    for tool,argv in INSTALL_FLATPAK.items():
        if have(tool): return argv
    return None

# ---------------------------------------------------------------------- reading
@dataclass
class AppsState:
    flatpak: bool                                  # the flatpak command is installed
    remote: set = field(default_factory=set)       # where Flathub is set up: {"user"}, {"system"}, both or neither
    catalog: Catalog | None = None
    installed: list = field(default_factory=list)
    problem: str = ""
    def is_installed(self, app_id): return next((i for i in self.installed if i.id==app_id),None)
    def __eq__(self, other):
        return isinstance(other,AppsState) and (self.flatpak,self.remote,self.catalog,self.installed,self.problem)==(other.flatpak,other.remote,other.catalog,other.installed,other.problem)

def read_state(env=None):
    if not have("flatpak"): return AppsState(False)
    state=AppsState(True)
    r=run(["flatpak","remotes","--columns=name,options"],timeout=15)
    if r.ok: state.remote=parse_remotes(r.out).get(REMOTE,set())
    else: state.problem=r.message
    r=run(["flatpak","list","--app","--columns=application,name,version,installation"],timeout=30)
    if r.ok: state.installed=parse_installed(r.out)
    elif not state.problem: state.problem=r.message
    arch=default_arch()
    for where in ("user","system"):   # this user's copy is the one `flatpak update --user --appstream` refreshes
        path,icons=appstream_file(where,arch,env)
        if path is not None:
            try: state.catalog=load_catalog(path,icons)
            except (OSError,ET.ParseError,EOFError) as exc: state.problem=f"Could not read the Flathub catalog: {exc}"; continue
            break
    return state
