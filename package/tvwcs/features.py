"""TVWCS's features that need extra software (Settings > Features), for a minimal install. No GTK dependency.

A minimal install (install.sh) has the Quick Menu, the applications list and the Settings pages that need nothing
more. Each feature below needs packages of its own; it can be turned on (its packages are installed first) or off
(its Settings page then only offers to turn it on, and its Quick Menu icon is not shown). Turning one off can also
uninstall its packages, but only those nothing else needs: TVWCS itself, another feature that is on, or any other
installed package (apt is asked what removing them would remove, and nothing else may go).

The choices are the "features" option: {key: False} for the features turned off; anything not listed is on.

`python3 -m tvwcs.features minimal` (run by install.sh) turns off the features whose software is missing;
`python3 -m tvwcs.features off` prints the features turned off, one per line."""
from __future__ import annotations
import os, re, shutil, subprocess, sys
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
    in_use: tuple = ()          # processes that, while running, mean its packages cannot be uninstalled from here

FEATURES=(
    Feature("sound","Sound","Volume, and the speakers, headphones and microphones to use (the Sound page and the Quick Menu's volume).",
            ("pipewire","pipewire-pulse","wireplumber","pulseaudio-utils"),(("cmd","pactl"),),("sound",)),
    Feature("bluetooth","Bluetooth","Pairing and connecting Bluetooth remotes, headphones and game controllers.",
            ("bluez",),(("cmd","bluetoothctl"),),("bluetooth",)),
    Feature("network","Network","Ethernet and Wi-Fi settings, with NetworkManager.",
            ("network-manager",),(("cmd","nmcli"),),("network",),in_use=("NetworkManager",)),
    Feature("storage","Storage","Mounting drives and switching them off, and network shares.",
            ("udisks2","gvfs-backends"),(("cmd","udisksctl"),),("storage",)),
    Feature("terminal","Terminal","A terminal inside Settings.",("gir1.2-vte-3.91",),(("gi","Vte","3.91"),),("terminal",)),
    Feature("apps","Apps from Flathub","Finding, installing and removing apps from Flathub.",("flatpak",),(("cmd","flatpak"),),("apps",)),
    Feature("screensaver","Screen saver","The bouncing logo after a time without input.",("python3-gi-cairo",),(("cairo",),)),
    Feature("lock_saver","Screen saver when locked","The screen saver while the computer is locked (xsecurelock; X11 only).",
            ("xsecurelock",),(("cmd","xsecurelock"),),x11_only=True),
    Feature("cursor","Hiding the mouse pointer","Hides the pointer after a few seconds without moving (unclutter; sway does it itself).",
            ("unclutter-xfixes",),(("cmd","unclutter"),),x11_only=True),
)
BY_KEY={f.key:f for f in FEATURES}
PAGE_FEATURE={p:f.key for f in FEATURES for p in f.pages}
# Packages TVWCS itself needs, even in a minimal install: never uninstalled from here
CORE_PACKAGES={"python3-gi","gir1.2-gtk-4.0","i3","sway","xdotool","x11-xserver-utils","xsettingsd","libxss1","swayidle","libglib2.0-bin",
               "adwaita-icon-theme","fonts-open-sans","xdg-desktop-portal","xdg-desktop-portal-gtk","xserver-xorg","xinit"}

def clean(raw):
    """The "features" option: only known keys, only False kept (on is the default)."""
    return {k:False for k,v in raw.items() if k in BY_KEY and v is False} if isinstance(raw,dict) else {}

def enabled(settings, key):
    return (settings.get("features") or {}).get(key,True) is not False

def page_enabled(settings, page_key):
    key=PAGE_FEATURE.get(page_key)
    return key is None or enabled(settings,key)

def sway(env=None):
    env=os.environ if env is None else env
    return bool(env.get("SWAYSOCK"))

def applies(feature, env=None):
    """Whether the feature means anything here (an X11-only one does not on sway)."""
    return not (feature.x11_only and sway(env))

# ---------------------------------------------------------------------- what is installed
LIBEXEC=("/usr/libexec","/usr/lib/gvfs","/usr/lib")
def _probe(p, which=shutil.which):
    kind=p[0]
    if kind=="cmd": return bool(which(p[1]))
    if kind=="libexec": return any(os.path.exists(os.path.join(d,p[1])) for d in LIBEXEC)
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
    """apt-get remove: only these packages (never autoremove or purge; their settings stay)."""
    if not packages or not all(VALID_PACKAGE.fullmatch(p) for p in packages): raise ValueError("Unexpected package name.")
    return ["env","DEBIAN_FRONTEND=noninteractive","apt-get","remove","-y",*packages]

def parse_simulated_removal(text):
    """`apt-get -s remove ...` -> the packages it would remove ("Remv name [version]" lines)."""
    return [line.split()[1] for line in text.splitlines() if line.startswith("Remv ") and len(line.split())>1]

def running(names, proc="/proc"):
    """The ones of `names` running now (by process name)."""
    found=set()
    try: pids=[e.name for e in os.scandir(proc) if e.name.isdigit()]
    except OSError: return []
    for pid in pids:
        try:
            with open(f"{proc}/{pid}/comm",encoding="utf-8",errors="replace") as f: comm=f.read().strip()
        except OSError: continue
        if comm in names: found.add(comm)
    return sorted(found)

def removable(feature, settings, run=subprocess.run, proc="/proc"):
    """(packages that can be uninstalled, "" or why nothing can be). Only installed packages of the feature that TVWCS
    and the other features that are on do not need, and that nothing else installed depends on."""
    if not shutil.which("apt-get"): return [],"Uninstalling needs apt (Debian and its family)."
    states=package_states(feature.packages,run)
    mine=[p for p in feature.packages if states.get(p)]
    if not mine: return [],"Its packages are not installed (or were installed some other way)."
    shared={p for f in FEATURES if f.key!=feature.key and enabled(settings,f.key) for p in f.packages}
    keep=[p for p in mine if p in CORE_PACKAGES or p in shared]
    mine=[p for p in mine if p not in keep]
    if not mine: return [],f"{', '.join(keep)} {'is' if len(keep)==1 else 'are'} needed by TVWCS or by another feature that is on."
    busy=running(feature.in_use,proc)
    if busy: return [],(f"{busy[0]} is running, and it may be what keeps this computer connected. Uninstalling it from here "
                        "could cut the connection, so it is not offered.")
    try: done=run(["apt-get","-s","remove",*mine],capture_output=True,text=True,timeout=60,env={**os.environ,"LC_ALL":"C"})
    except (OSError,subprocess.SubprocessError) as exc: return [],f"apt could not be asked: {exc}"
    if done.returncode: return [],(done.stderr or done.stdout or "apt could not work out what would be removed.").strip()[-400:]
    others=[p for p in parse_simulated_removal(done.stdout) if p.split(":")[0] not in mine]
    if others:
        shown=", ".join(others[:6])+(f" and {len(others)-6} more" if len(others)>6 else "")
        return [],f"Other software needs them: uninstalling would also remove {shown}. Nothing was changed."
    return mine,""

# ---------------------------------------------------------------------- install.sh's helpers
def _store():
    from tvwcs.model import ConfigStore
    return ConfigStore()

def main(argv):
    if argv==["minimal"]:   # a minimal install: the features whose software is missing start off
        store=_store(); off=dict(store.settings.get("features") or {})
        for f in FEATURES:
            if applies(f) and not installed(f): off[f.key]=False
        store.settings["features"]=clean(off); store.save()
        for key in store.settings["features"]: print(f"Turned off: {BY_KEY[key].label} (turn it on in Settings > Features)")
        return 0
    if argv==["off"]:
        for key in clean(_store().settings.get("features")): print(key)
        return 0
    print("Usage: python3 -m tvwcs.features minimal|off",file=sys.stderr); return 2

if __name__=="__main__": sys.exit(main(sys.argv[1:]))
