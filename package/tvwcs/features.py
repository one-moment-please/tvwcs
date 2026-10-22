"""The software each part of TVWCS needs beyond a basic install. No GTK dependency.

The installer installs what the Quick Menu, the applications list and Settings need. Each entry below needs packages
of its own; a Settings page whose software is missing offers to install it (Sound installs PipeWire, Apps installs
Flatpak and adds Flathub, and so on), and its Quick Menu icon is not shown until then. There is no on/off switch: what
is installed is used. (Before 4.0 there was a Features page with one.)"""
from __future__ import annotations
import os, re, shutil, subprocess
from dataclasses import dataclass

@dataclass(frozen=True)
class Feature:
    key: str
    label: str
    what: str                   # what it gives, one sentence
    packages: tuple             # Debian packages
    probes: tuple               # ("cmd", name) | ("gi", namespace, version) | ("cairo",) | ("libexec", name): all must pass
    pages: tuple = ()           # the Settings pages it brings
    x11_only: bool = False
    sway_only: bool = False

FEATURES=(
    Feature("sound","Sound","Volume, and the speakers, headphones and microphones to use (the Sound page and the Quick Menu's volume).",
            ("pipewire","pipewire-pulse","wireplumber","pulseaudio-utils"),(("cmd","pactl"),),("sound",)),
    Feature("bluetooth","Bluetooth","Pairing and connecting Bluetooth remotes, headphones and game controllers.",
            ("bluez",),(("cmd","bluetoothctl"),),("bluetooth",)),
    Feature("samba","Network shares (Samba)","Connecting to Windows and Samba shares, and NFS, SSH and FTP ones, on the Storage page.",
            ("gvfs-backends",),(("libexec","gvfsd-smb"),)),
    Feature("terminal","Terminal","A terminal inside Settings.",("gir1.2-vte-3.91",),(("gi","Vte","3.91"),),("terminal",)),
    Feature("apps","Apps from Flathub","Finding, installing and removing apps from Flathub.",("flatpak",),(("cmd","flatpak"),),("apps",)),
    Feature("screensaver","Screen saver","The bouncing logo after a time without input.",("python3-gi-cairo",),(("cairo",),)),
    Feature("sway_saver","Screen saver on sway","The screen saver drawn over every window on sway (gtk4-layer-shell).",
            ("gir1.2-gtk4layershell-1.0","libgtk4-layer-shell0"),(("typelib","Gtk4LayerShell-1.0"),("lib","libgtk4-layer-shell.so.0")),sway_only=True),
    Feature("lock_saver","Screen saver when locked","The screen saver while the computer is locked (xsecurelock; X11 only).",
            ("xsecurelock",),(("cmd","xsecurelock"),),x11_only=True),
    Feature("cursor","Hiding the mouse pointer","Hides the pointer after a few seconds without moving (unclutter; sway does it itself).",
            ("unclutter-xfixes",),(("cmd","unclutter"),),x11_only=True),
)
BY_KEY={f.key:f for f in FEATURES}
PAGE_FEATURE={p:f.key for f in FEATURES for p in f.pages}

def sway(env=None):
    env=os.environ if env is None else env
    return bool(env.get("SWAYSOCK"))

def applies(feature, env=None):
    """Whether the feature means anything here (an X11-only one does not on sway)."""
    return not (feature.x11_only and sway(env)) and not (feature.sway_only and not sway(env))

def screensaver(env=None):
    """The screen saver's software here: on sway it also needs gtk4-layer-shell, to draw over every window."""
    f=BY_KEY["screensaver"]
    if not sway(env): return f
    extra=BY_KEY["sway_saver"]
    return Feature(f.key,f.label,f.what,f.packages+extra.packages,f.probes+extra.probes)

# ---------------------------------------------------------------------- what is installed
LIBEXEC=("/usr/libexec","/usr/lib/gvfs","/usr/lib")
def _probe(p, which=shutil.which):
    kind=p[0]
    if kind=="cmd": return bool(which(p[1]))
    if kind=="libexec": return any(os.path.exists(os.path.join(d,p[1])) for d in LIBEXEC)
    if kind=="lib":   # Debian's gir1.2-gtk4layershell-1.0 does not depend on the library it describes
        import glob
        return bool(glob.glob(f"/usr/lib/*/{p[1]}")+glob.glob(f"/usr/lib*/{p[1]}"))
    if kind=="typelib":   # found without loading it (gtk4-layer-shell must not be loaded after GTK)
        import glob
        return bool(glob.glob(f"/usr/lib/*/girepository-1.0/{p[1]}.typelib")+glob.glob(f"/usr/lib*/girepository-1.0/{p[1]}.typelib"))
    try:
        import gi
        if kind=="gi": gi.require_version(p[1],p[2]); __import__("gi.repository."+p[1]); return True
        if kind=="cairo": gi.require_foreign("cairo"); return True
    except (ImportError,ValueError,AttributeError): return False
    return False

def installed(feature, which=shutil.which):
    """Its software is there (what it runs, not the package names: another distribution's packages count too)."""
    return all(_probe(p,which) for p in feature.probes)

def package_states(packages, run=subprocess.run):
    """{package: installed?} from dpkg; {} without dpkg."""
    if not shutil.which("dpkg-query"): return {}
    try: out=run(["dpkg-query","-W","-f=${Package}\t${db:Status-Abbrev}\n",*packages],capture_output=True,text=True,timeout=20).stdout
    except (OSError,subprocess.SubprocessError): return {}
    states={p:False for p in packages}
    for line in out.splitlines():
        name,_tab,status=line.partition("\t")
        if name in states: states[name]=status.startswith("ii")
    return states

def missing_packages(feature, run=subprocess.run):
    states=package_states(feature.packages,run)
    return [p for p in feature.packages if not states.get(p,False)] if states else list(feature.packages)

VALID_PACKAGE=re.compile(r"[a-z0-9][a-z0-9+.-]*")
# Packages apt would bring in with one of ours (as recommended) that change other desktops too: unclutter-startup starts
# unclutter in every X session, not only TVWCS's. Left out ("name-" tells apt not to install it) unless already there.
NOT_WITH={"unclutter-xfixes":"unclutter-startup"}
def install_argv(packages, run=subprocess.run):
    if not packages or not all(VALID_PACKAGE.fullmatch(p) for p in packages): raise ValueError("Unexpected package name.")
    unwanted=[NOT_WITH[p] for p in packages if p in NOT_WITH]
    states=package_states(unwanted,run) if unwanted else {}
    skip=[f"{u}-" for u in unwanted if states.get(u) is False]
    return ["env","DEBIAN_FRONTEND=noninteractive","sh","-c",'apt-get update -q && apt-get install -y "$@"',"sh",*packages,*skip]

def remove_argv(packages):
    """apt-get removes the packages (their settings stay, as with `apt-get remove`)."""
    if not packages or not all(VALID_PACKAGE.fullmatch(p) for p in packages): raise ValueError("Unexpected package name.")
    return ["env","DEBIAN_FRONTEND=noninteractive","apt-get","remove","-y",*packages]

def parse_removals(text):
    """`apt-get -s remove ...`: the packages it would remove ("Remv name [version]" lines)."""
    return [line.split()[1] for line in text.splitlines() if line.startswith("Remv ") and len(line.split())>1]

def removals(packages, run=subprocess.run):
    """Every package removing these would take with it (they depend on them), the packages themselves first; [] when
    apt cannot tell."""
    if not shutil.which("apt-get"): return []
    try: out=run(["apt-get","-s","remove",*packages],capture_output=True,text=True,timeout=60,env={**os.environ,"LC_ALL":"C"}).stdout
    except (OSError,subprocess.SubprocessError): return []
    found=parse_removals(out)
    return [p for p in packages if p in found]+[p for p in found if p not in packages]

