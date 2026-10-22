"""The software each part of TVWCS needs beyond a basic install. No GTK dependency.

The installer installs what the Quick Menu, the applications list and Settings need. Each entry below needs packages
of its own; a Settings page whose software is missing offers to install it (Sound installs PipeWire, Bluetooth installs
BlueZ), and its Quick Menu icon is not shown until then. There is no on/off switch: what
is installed is used. (Before 4.0 there was a Features page with one.)"""
from __future__ import annotations
import re, shutil, subprocess
from dataclasses import dataclass

@dataclass(frozen=True)
class Feature:
    key: str
    label: str
    what: str                   # what it gives, one sentence
    packages: tuple             # Debian packages
    probes: tuple               # ("cmd", name) | ("gi", namespace, version): all must pass
    pages: tuple = ()           # the Settings pages it brings

FEATURES=(
    Feature("sound","Sound","Volume, and the speakers, headphones and microphones to use (the Sound page and the Quick Menu's volume).",
            ("pipewire","pipewire-pulse","wireplumber","pulseaudio-utils"),(("cmd","pactl"),),("sound",)),
    Feature("bluetooth","Bluetooth","Pairing and connecting Bluetooth remotes, headphones and game controllers.",
            ("bluez",),(("cmd","bluetoothctl"),),("bluetooth",)),
)
BY_KEY={f.key:f for f in FEATURES}
PAGE_FEATURE={p:f.key for f in FEATURES for p in f.pages}

# ---------------------------------------------------------------------- what is installed
def _probe(p, which=shutil.which):
    if p[0]=="cmd": return bool(which(p[1]))
    try:
        import gi
        if p[0]=="gi": gi.require_version(p[1],p[2]); __import__("gi.repository."+p[1]); return True
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
def install_argv(packages):
    if not packages or not all(VALID_PACKAGE.fullmatch(p) for p in packages): raise ValueError("Unexpected package name.")
    return ["env","DEBIAN_FRONTEND=noninteractive","sh","-c",'apt-get update -q && apt-get install -y "$@"',"sh",*packages]

def remove_argv(packages):
    """apt-get removes the packages (their settings stay, as with `apt-get remove`)."""
    if not packages or not all(VALID_PACKAGE.fullmatch(p) for p in packages): raise ValueError("Unexpected package name.")
    return ["env","DEBIAN_FRONTEND=noninteractive","apt-get","remove","-y",*packages]
