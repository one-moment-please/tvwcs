"""Software updates for Settings: the distribution's package manager (apt, or pacman on Arch). No GTK dependency.

Listing the waiting updates never needs root. Installing them does: the panel runs the `install` command through
sudo or doas (see privilege.py and ui_control.py)."""
from __future__ import annotations
import os, platform, re, time
from dataclasses import dataclass, field

from tvwcs.control_cmd import have, run

@dataclass(frozen=True)
class Update:
    name: str
    new: str
    old: str = ""
    source: str = ""     # the repository

@dataclass(frozen=True)
class Manager:
    id: str
    label: str
    list_argv: tuple
    parse: object        # text -> [Update]
    install_argv: tuple  # runs as root
    needs_root: bool = True
    ok_codes: tuple = (0,)   # exit codes of list_argv that mean "it worked" (some exit non-zero when updates wait)
    refresh_argv: tuple = () # downloads fresh package lists, as root, where listing alone reads the cached ones
    fresh_lists: bool = False  # listing downloads fresh package lists itself (pacman's checkupdates)

@dataclass
class UpdatesState:
    available: bool
    message: str = ""
    manager: Manager | None = None
    updates: list = field(default_factory=list)
    problems: list = field(default_factory=list)   # a list command that failed: (label, message)
    checked: float | None = None                   # when the package lists were last downloaded (epoch seconds)
    @property
    def total(self): return len(self.updates)

# ------------------------------------------------------------------ parsing (pure)
_APT=re.compile(r"^(\S+?)/(\S+)\s+(\S+)\s+\S+(?:\s+\[upgradable from:\s*([^\]]+)\])?")
def parse_apt(text):
    """`apt list --upgradable`: 'bash/noble-updates 5.2.21-2ubuntu4.1 amd64 [upgradable from: 5.2.21-2ubuntu4]'."""
    found=[]
    for line in text.splitlines():
        m=_APT.match(line.strip())
        if m: found.append(Update(m.group(1),m.group(3),(m.group(4) or "").strip(),m.group(2).split(",")[0]))
    return found

_PACMAN=re.compile(r"^(\S+)\s+(\S+)\s+->\s+(\S+)")
def parse_pacman(text):
    """`checkupdates`: 'linux 6.9.7.arch1-1 -> 6.9.8.arch1-1' (one held back by IgnorePkg ends in '[ignored]' and is left out)."""
    found=[]
    for line in text.splitlines():
        m=_PACMAN.match(line.strip())
        if m and "[ignored]" not in line: found.append(Update(m.group(1),m.group(3),m.group(2)))
    return found

_APT_INSTALL=("env","DEBIAN_FRONTEND=noninteractive","sh","-c",
              "apt-get update && apt-get -y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold upgrade --with-new-pkgs")
MANAGERS=(
    Manager("apt","APT",("apt","list","--upgradable"),parse_apt,_APT_INSTALL,refresh_argv=("apt-get","update")),
    # checkupdates (pacman-contrib) downloads fresh lists into a copy of pacman's database, so listing never leaves the
    # real one half updated; it exits 2 when nothing waits. Installing is always a full upgrade: Arch has no other kind.
    Manager("pacman","pacman",("checkupdates",),parse_pacman,("pacman","-Syu","--noconfirm"),ok_codes=(0,2),fresh_lists=True),
)
_TOOL={"apt":"apt-get","pacman":"pacman"}

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

_LISTS={"apt":("/var/lib/apt/lists","/var/cache/apt/pkgcache.bin"),"pacman":("/var/lib/pacman/sync",)}
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
    if manager.id=="pacman" and not have("checkupdates"): return [],"checkupdates is not installed: install pacman-contrib."
    result=run(list(manager.list_argv),timeout=240)
    if result.code not in manager.ok_codes: return [],result.message
    return manager.parse(result.out),""

def read_state():
    manager=detect()
    if manager is None: return UpdatesState(False,"No supported package manager was found (apt on Debian and its family, pacman on Arch).")
    state=UpdatesState(True,"",manager)
    state.updates,problem=_list(manager)
    state.checked=time.time() if manager.fresh_lists and not problem else lists_checked(manager)
    if problem: state.problems.append((manager.label,problem))
    return state
