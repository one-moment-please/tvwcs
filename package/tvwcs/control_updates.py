"""Software updates for Settings: the distribution's package manager (apt), plus Flatpak. No GTK dependency.

Listing the waiting updates never needs root. Installing them does: the panel runs the `install` command through
sudo or doas (see privilege.py and ui_control.py), and Flatpak's own update as the user."""
from __future__ import annotations
import os, platform, re, time
from dataclasses import dataclass, field

from tvwcs.control_cmd import have, run

@dataclass(frozen=True)
class Update:
    name: str
    new: str
    old: str = ""
    source: str = ""     # the repository, or Flatpak's remote

@dataclass(frozen=True)
class Manager:
    id: str
    label: str
    list_argv: tuple
    parse: object        # text -> [Update]
    install_argv: tuple  # runs as root (or as the user, for Flatpak)
    needs_root: bool = True
    ok_codes: tuple = (0,)   # exit codes of list_argv that mean "it worked" (some exit non-zero when updates wait)
    refresh_argv: tuple = () # downloads fresh package lists, as root, where listing alone reads the cached ones

@dataclass
class UpdatesState:
    available: bool
    message: str = ""
    manager: Manager | None = None
    updates: list = field(default_factory=list)
    flatpak: list = field(default_factory=list)
    problems: list = field(default_factory=list)   # a list command that failed: (label, message)
    checked: float | None = None                   # when the package lists were last downloaded (epoch seconds)
    @property
    def total(self): return len(self.updates)+len(self.flatpak)

# ------------------------------------------------------------------ parsing (pure)
_APT=re.compile(r"^(\S+?)/(\S+)\s+(\S+)\s+\S+(?:\s+\[upgradable from:\s*([^\]]+)\])?")
def parse_apt(text):
    """`apt list --upgradable`: 'bash/noble-updates 5.2.21-2ubuntu4.1 amd64 [upgradable from: 5.2.21-2ubuntu4]'."""
    found=[]
    for line in text.splitlines():
        m=_APT.match(line.strip())
        if m: found.append(Update(m.group(1),m.group(3),(m.group(4) or "").strip(),m.group(2).split(",")[0]))
    return found

def parse_flatpak(text):
    """`flatpak remote-ls --updates --columns=application,version,origin` (tab separated)."""
    found=[]
    for line in text.splitlines():
        cols=line.split("\t")
        if cols and cols[0].strip() and "." in cols[0] and not cols[0].startswith("Application"):
            found.append(Update(cols[0].strip(),(cols[1].strip() if len(cols)>1 else ""),"",(cols[2].strip() if len(cols)>2 else "Flatpak")))
    return found

_APT_INSTALL=("env","DEBIAN_FRONTEND=noninteractive","sh","-c",
              "apt-get update && apt-get -y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold upgrade --with-new-pkgs")
MANAGERS=(
    Manager("apt","APT",("apt","list","--upgradable"),parse_apt,_APT_INSTALL,refresh_argv=("apt-get","update")),
)
FLATPAK=Manager("flatpak","Flatpak",("flatpak","remote-ls","--updates","--columns=application,version,origin"),parse_flatpak,
                ("flatpak","update","-y","--noninteractive"),needs_root=False)
_TOOL={"apt":"apt-get"}

def detect(which=None):
    """The system's package manager (the first found), or None."""
    kwargs={} if which is None else {"which":which}
    return next((m for m in MANAGERS if have(_TOOL[m.id],**kwargs)),None)

def age_text(checked, now=None):
    """Seconds since the lists were downloaded -> 'just now' / '5 minutes ago' / '3 hours ago' / '2 days ago'."""
    if checked is None: return ""
    seconds=max(0,(now if now is not None else time.time())-checked)
    for size,unit in ((86400,"day"),(3600,"hour"),(60,"minute")):
        if seconds>=size:
            n=int(seconds//size); return f"{n} {unit}{'s' if n!=1 else ''} ago"
    return "just now"

_LISTS={"apt":("/var/lib/apt/lists","/var/cache/apt/pkgcache.bin")}
def lists_checked(manager):
    times=[]
    for path in _LISTS.get(manager.id,()):
        try: times.append(os.stat(path).st_mtime)
        except OSError: pass
    return max(times) if times else None

def reboot_needed(release=None, exists=os.path.exists):
    """Debian and Ubuntu leave a marker; elsewhere, an updated kernel removes the running one's modules folder."""
    release=release or platform.release()
    if exists("/run/reboot-required") or exists("/var/run/reboot-required"): return True
    return not any(exists(f"{d}/{release}") for d in ("/usr/lib/modules","/lib/modules")) and exists("/usr/lib/modules")

def _list(manager):
    result=run(list(manager.list_argv),timeout=240)
    if result.code not in manager.ok_codes: return [],result.message
    return manager.parse(result.out),""

def read_state():
    manager=detect(); flatpak=have("flatpak")
    if manager is None and not flatpak:
        return UpdatesState(False,"No supported package manager was found (apt on Debian and its family, or Flatpak).")
    state=UpdatesState(True,"",manager)
    if manager is not None:
        state.updates,problem=_list(manager); state.checked=lists_checked(manager)
        if problem: state.problems.append((manager.label,problem))
    if flatpak:
        state.flatpak,problem=_list(FLATPAK)
        if problem: state.problems.append(("Flatpak",problem))
    return state
