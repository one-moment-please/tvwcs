"""Software updates for Settings: the distribution's package manager (apt, or pacman on Arch). No GTK dependency.

Listing the waiting updates never needs root. Installing them does: the panel runs the `install` command through
sudo or doas (see privilege.py and ui_control.py).

On Arch, an update can also run step by step: pacman without --noconfirm, with each question it asks (parse_prompt)
answered with buttons. The page also shows Arch's news since the last full upgrade (read_news, last_upgrade) and the
.pacnew files updates left in /etc (pacnew_files)."""
from __future__ import annotations
import html, os, platform, re, time, urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime

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
    step_argv: tuple = ()    # installs them asking each question (answered from the page), as root; () when it can't

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
    Manager("pacman","pacman",("checkupdates",),parse_pacman,("pacman","-Syu","--noconfirm"),ok_codes=(0,2),fresh_lists=True,
            step_argv=("pacman","-Syu")),
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

# ------------------------------------------------------------------ step by step (pacman's questions)
@dataclass(frozen=True)
class Prompt:
    question: str
    answers: tuple   # (button label, what to type), the default first
    back: str = ""   # what Back (Esc) types: "n" for a yes/no question, so leaving never says yes

PROMPT_END=re.compile(r"(\[[Yy]/[Nn]\]|Enter a number \(default=\d+\):|Enter a selection \(default=all\):)\s*$")
_PROVIDERS=re.compile(r"There (?:are|is) \d+ providers? available for (\S+?):?\s*$")
_GROUP=re.compile(r"There (?:are|is) \d+ members? in group (\S+?):?\s*$")
_CHOICE=re.compile(r"(\d+)\)\s+(\S+)")

def is_prompt(text): return bool(PROMPT_END.search(text or ""))

def parse_prompt(text, recent=()):
    """One of pacman's questions (the unfinished line it waits on), with the buttons that answer it. recent: the
    lines printed before it, where a choice between providers lists its options. None when it is not a question."""
    line=(text or "").strip()
    q=re.sub(r"^::\s*","",line)
    if re.search(r"\[Y/n\]\s*$",line): return Prompt(re.sub(r"\s*\[Y/n\]\s*$","",q),(("Yes","y"),("No","n")),"n")
    if re.search(r"\[y/N\]\s*$",line): return Prompt(re.sub(r"\s*\[y/N\]\s*$","",q),(("No","n"),("Yes","y")),"n")
    m=re.search(r"Enter a number \(default=(\d+)\):\s*$",line)
    if m:
        default=m.group(1); head="Choose which package to install."; choices=[]
        for l in recent:
            h=_PROVIDERS.search(l)
            if h: head=f"There is more than one package that provides {h.group(1)}. Choose one."; choices=[]; continue
            choices+=_CHOICE.findall(l)
        answers=[(f"{name} (default)" if n==default else name,n) for n,name in choices]
        answers.sort(key=lambda a:a[1]!=default)
        return Prompt(head,tuple(answers) or ((f"Number {default} (default)",""),),"")
    if re.search(r"Enter a selection \(default=all\):\s*$",line):
        group=next((g.group(1) for l in reversed(list(recent)) for g in [_GROUP.search(l)] if g),"")
        return Prompt(f"Install every package in the group {group}?" if group else "Install every package in the group?",(("All (default)",""),),"")
    return None

# ------------------------------------------------------------------ Arch's news and .pacnew files
NEWS_URL="https://archlinux.org/feeds/news/"
NEWS_CACHE=3600
@dataclass(frozen=True)
class News:
    title: str
    date: float      # epoch seconds
    link: str
    text: str        # the article as plain text

def _plain(fragment):
    text=re.sub(r"<\s*(br|/p|/li|/h\d)\s*/?>","\n",fragment or "",flags=re.I)
    text=re.sub(r"<li[^>]*>","\n• ",text,flags=re.I)
    text=html.unescape(re.sub(r"<[^>]+>","",text))
    return re.sub(r"\n{3,}","\n\n",text).strip()

def parse_news(xml_text):
    """Arch's news feed (RSS), newest first. [] when it cannot be read."""
    try: root=ET.fromstring(xml_text)
    except ET.ParseError: return []
    found=[]
    for item in root.iter("item"):
        try: when=parsedate_to_datetime(item.findtext("pubDate") or "").timestamp()
        except (TypeError,ValueError): continue
        found.append(News((item.findtext("title") or "").strip(),when,(item.findtext("link") or "").strip(),_plain(item.findtext("description"))))
    return sorted(found,key=lambda n:n.date,reverse=True)

_news=(0.0,None)
def read_news(now=None, fetch=None):
    """Arch's news, fetched at most once an hour; None when it could not be fetched (offline, say)."""
    global _news
    now=time.time() if now is None else now
    if _news[1] is not None and now-_news[0]<NEWS_CACHE: return _news[1]
    try:
        if fetch is None:
            req=urllib.request.Request(NEWS_URL,headers={"User-Agent":"TVWCS-settings"})
            with urllib.request.urlopen(req,timeout=8) as r: text=r.read(2_000_000).decode("utf-8","replace")
        else: text=fetch(NEWS_URL)
    except (OSError,ValueError): return None
    items=parse_news(text); _news=(now,items); return items

_UPGRADE=re.compile(r"^\[([^\]]+)\] \[PACMAN\] starting full system upgrade")
def last_upgrade(log="/var/log/pacman.log"):
    """When the last full upgrade (pacman -Syu) started, from pacman's log; None when it says nothing."""
    try:
        with open(log,"rb") as f:
            f.seek(0,2); f.seek(max(0,f.tell()-4_000_000)); text=f.read().decode("utf-8","replace")
    except OSError: return None
    for line in reversed(text.splitlines()):
        m=_UPGRADE.match(line)
        if not m: continue
        for fmt in ("%Y-%m-%dT%H:%M:%S%z","%Y-%m-%d %H:%M"):
            try:
                when=datetime.strptime(m.group(1),fmt)
                return when.timestamp()
            except ValueError: continue
    return None

def news_since(items, since, keep=5):
    """The news posted after `since` (the last full upgrade), at most `keep`; without a date, the newest one."""
    if not items: return []
    if since is None: return list(items[:1])
    return [n for n in items if n.date>since][:keep]

def pacnew_files(root="/etc", limit=50):
    """Config files an update could not replace because they had been changed: pacman put the new default next to
    each as <name>.pacnew, to be merged by hand (pacdiff, from pacman-contrib, helps)."""
    found=[]
    for folder,dirs,files in os.walk(root,onerror=lambda _e:None):
        dirs.sort()
        found+=[os.path.join(folder,f) for f in sorted(files) if f.endswith(".pacnew")]
        if len(found)>=limit: break
    return found[:limit]
