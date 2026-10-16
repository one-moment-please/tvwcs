"""TVWCS's login screen (Settings > Features > Login screen), and the computer's automatic login. No GTK dependency.

The login screen is greetd (the login daemon) running TVWCS's greeter (ui_greeter.py) full screen in cage, a kiosk
Wayland compositor. greetd checks the password and starts the session; the greeter only draws the screen. It starts
X sessions such as i3 through startx and Wayland ones such as sway directly, so it can start either (unlike LightDM,
which cannot start sway reliably).

The greeter runs as greetd's own user, which cannot read anyone's home folder, so TVWCS keeps a copy of itself in
/usr/local/lib/tvwcs-greeter and the look it shows (accent colour, light or dark, TV or desktop size) in
/etc/tvwcs/login-screen.json. The greeter remembers the last user, and each user's session and keyboard, in
/var/lib/tvwcs-greeter.

Turning it on keeps the login screen that was used before installed, and remembers it, so turning it off goes back to
it. Changes take effect at the next start: a running login screen (and the session it started) is never stopped.

The automatic login is set where the login screen in use keeps it: greetd's initial session (the TVWCS login screen
then shows only after logging out), LightDM's and SDDM's own settings, or, without a login screen, the first console's
automatic login (getty) and a few lines in the login shell's profile that start i3 or sway there (as install.sh does).

Changing the system needs root: `python3 -m tvwcs.loginscreen <command>` is what Settings and install.sh run as root.
TVWCS_ROOT puts every system path under another folder (the tests), and then nothing is run."""
from __future__ import annotations
import json, os, pwd, re, shlex, shutil, subprocess, sys
from pathlib import Path

GREETER_LIB="/usr/local/lib/tvwcs-greeter"        # TVWCS's copy for the greeter: tvwcs/ (the package), greeter, start-session
LOOK="/etc/tvwcs/login-screen.json"                # what the greeter looks like
PREVIOUS="/etc/tvwcs/previous-login-screen"        # the login screen (systemd unit name) used before TVWCS's, "" for none
STATE_DIR="/var/lib/tvwcs-greeter"                 # the greeter's memory (owned by greetd's user)
GREETD_CONF="/etc/greetd/config.toml"
GREETD_BACKUP="/etc/greetd/config.toml.tvwcs-backup"   # greetd's own config from before (another greeter's)
GREETD_USER="_greetd"                              # Debian's greetd user
GREETD_VT=7                                        # Debian's greetd runs on the seventh console, like other login screens
PACKAGES=("greetd","cage")                         # what the login screen needs besides TVWCS's own GTK packages
GETTY_OVERRIDE="/etc/systemd/system/getty@tty1.service.d/autologin.conf"   # install.sh's console login
LIGHTDM_AUTOLOGIN="/etc/lightdm/lightdm.conf.d/50-tvwcs-autologin.conf"
SDDM_AUTOLOGIN="/etc/sddm.conf.d/50-tvwcs-autologin.conf"
SESSION_DIRS=(("/usr/share/xsessions","x11"),("/usr/local/share/xsessions","x11"),
              ("/usr/share/wayland-sessions","wayland"),("/usr/local/share/wayland-sessions","wayland"))
UNIT_DIRS=("/etc/systemd/system","/usr/lib/systemd/system","/lib/systemd/system")
GREETER_MARK="tvwcs-greeter/greeter"            # greetd's config runs TVWCS's greeter when its command has this

# Login screens, by systemd unit. wayland: it can start Wayland sessions such as sway reliably. TVWCS can set the
# automatic login of greetd (its own login screen only), LightDM and SDDM.
KNOWN={"gdm3":("GNOME's login screen (GDM)",True),"gdm":("GNOME's login screen (GDM)",True),"sddm":("SDDM",True),
       "lightdm":("LightDM",False),"lxdm":("LXDM",False),"xdm":("XDM",False),"slim":("SLiM",False),"greetd":("greetd",True),
       "ly":("Ly",True),"emptty":("emptty",True),"nodm":("nodm",False),"entrance":("Entrance",False),"lemurs":("lemurs",True)}
# The standard login screens TVWCS offers to install instead: (unit, packages). SDDM starts sway too; LightDM only X.
STANDARD={"sddm":("sddm",),"lightdm":("lightdm","lightdm-gtk-greeter")}

def path(p) -> Path:
    """A system path, under TVWCS_ROOT when the tests set it."""
    return Path(os.environ.get("TVWCS_ROOT","")+p)

def name(unit) -> str:
    """A login screen's name for people."""
    if unit=="tvwcs": return "TVWCS's login screen"
    return KNOWN.get(unit,(unit or "no login screen",False))[0]

def wayland_ok(unit) -> bool:
    """Whether this login screen can start sway. No login screen at all can (from the console)."""
    return unit in ("","tvwcs") or KNOWN.get(unit,("",False))[1]

# ---------------------------------------------------------------------- what is here
def _read(p, default=""):
    try: return path(p).read_text(encoding="utf-8")
    except OSError: return default

def active_unit() -> str:
    """The login screen that runs at start-up, by unit name (lightdm, gdm3, greetd...), or "" for none."""
    link=path("/etc/systemd/system/display-manager.service")
    if link.is_symlink():
        target=os.readlink(link); unit=os.path.basename(target)
        return unit[:-len(".service")] if unit.endswith(".service") else unit
    first=_read("/etc/X11/default-display-manager").strip()
    return os.path.basename(first) if first else ""

def greetd_config() -> dict:
    """greetd's config, as {section: {key: value}} (a small TOML reader: greetd's config is flat)."""
    out={}; section=""
    for line in _read(GREETD_CONF).splitlines():
        line=line.strip()
        if not line or line.startswith("#"): continue
        m=re.fullmatch(r"\[([A-Za-z0-9_.-]+)\]",line)
        if m: section=m.group(1); out.setdefault(section,{}); continue
        m=re.fullmatch(r"([A-Za-z0-9_]+)\s*=\s*(.+?)\s*(#.*)?",line)
        if not m: continue
        raw=m.group(2)
        if raw.startswith('"') and raw.endswith('"'):
            try: value=json.loads(raw)
            except ValueError: value=raw[1:-1]
        elif raw.isdigit(): value=int(raw)
        elif raw in ("true","false"): value=raw=="true"
        else: value=raw
        out.setdefault(section,{})[m.group(1)]=value
    return out

def greetd_is_ours(config=None) -> bool:
    config=greetd_config() if config is None else config
    return GREETER_MARK in str(config.get("default_session",{}).get("command",""))

def current() -> str:
    """The login screen in use: "tvwcs" for TVWCS's own, else its unit name, "" for none."""
    unit=active_unit()
    return "tvwcs" if unit=="greetd" and greetd_is_ours() else unit

def unit_installed(unit) -> bool:
    return any(path(f"{d}/{unit}.service").exists() for d in UNIT_DIRS)

def installed_screens() -> list:
    """The login screens installed here, other than TVWCS's (greetd counts only with another greeter's config to go
    back to)."""
    found=[]
    for unit in KNOWN:
        if not unit_installed(unit): continue
        if unit=="greetd" and not (path(GREETD_BACKUP).exists() or not greetd_is_ours()): continue
        if unit=="gdm" and "gdm3" in found: continue
        found.append(unit)
    return found

def previous() -> str:
    """The login screen used before TVWCS's, when it is still installed; else ""."""
    unit=_read(PREVIOUS).strip()
    return unit if unit and unit in installed_screens() else ""

def fallback() -> str:
    """What turning TVWCS's login screen off goes back to: the one used before it, else another installed one, else ""."""
    return previous() or next(iter(installed_screens()),"")

def installed_version() -> str:
    return _read(f"{GREETER_LIB}/VERSION").strip()

def read_look() -> dict:
    try: raw=json.loads(_read(LOOK,"{}"))
    except ValueError: raw={}
    return look_from(raw if isinstance(raw,dict) else {})

def look_from(settings) -> dict:
    """The login screen's look, from TVWCS's settings (or the look file)."""
    accent=settings.get("accent"); accent=accent if isinstance(accent,str) and re.fullmatch(r"#[0-9a-fA-F]{6}",accent) else "#0078d7"
    theme=settings.get("theme") if settings.get("theme") in ("dark","light") else "dark"
    scale=settings.get("scale") if settings.get("scale") in ("desktop","tenfoot","tenfoot_4k") else "desktop"
    return {"accent":accent.lower(),"theme":theme,"scale":scale}

def status(version="", settings=None) -> dict:
    """What Settings shows: the login screen in use, whether it is TVWCS's, and whether TVWCS's copy is up to date
    (`version`, the running TVWCS's) and shows the look of `settings`."""
    cur=current(); ours=cur=="tvwcs"
    return {"current":cur,"ours":ours,"fallback":fallback() if ours else "","installed":installed_screens(),
            "outdated":ours and bool(version) and installed_version()!=version,
            "look_changed":ours and settings is not None and read_look()!=look_from(settings),
            "packages":[p for p in PACKAGES if not shutil.which(p,path=f"{path('/usr/sbin')}:{path('/usr/bin')}")]}

# ---------------------------------------------------------------------- sessions (shared with the greeter)
def _desktop_entry(text):
    """The [Desktop Entry] keys of a .desktop file."""
    keys={}; inside=False
    for line in text.splitlines():
        line=line.strip()
        if line.startswith("["): inside=line=="[Desktop Entry]"; continue
        if inside and "=" in line and not line.startswith("#"):
            k,_,v=line.partition("="); keys.setdefault(k.strip(),v.strip())
    return keys

def sessions(which=shutil.which) -> list:
    """The sessions the login screen can start: [{id, name, kind (x11|wayland), exec, desktop}], TVWCS's first, then
    i3 and sway, then the rest by name. Hidden ones, and ones whose program is not installed, are left out."""
    found={}
    for d,kind in SESSION_DIRS:
        try: files=sorted(path(d).glob("*.desktop"))
        except OSError: continue
        for f in files:
            sid=f.stem
            if sid in found: continue
            try: e=_desktop_entry(f.read_text(encoding="utf-8",errors="replace"))
            except OSError: continue
            if e.get("Hidden","").lower()=="true" or e.get("NoDisplay","").lower()=="true" or not e.get("Exec"): continue
            try: argv=shlex.split(e["Exec"])
            except ValueError: continue
            if not argv: continue
            tryexec=e.get("TryExec") or argv[0]
            if not (os.path.isabs(tryexec) and path(tryexec).exists() or which(tryexec)): continue
            found[sid]={"id":sid,"name":e.get("Name") or sid,"kind":kind,"exec":argv,"desktop":e.get("DesktopNames","").rstrip(";").split(";")[0] or sid}
    def order(s):
        return (0 if s["id"].startswith("tvwcs-") else 1 if s["id"] in ("i3","sway") else 2, s["name"].casefold())
    return sorted(found.values(),key=order)

def start_session_argv(session) -> list:
    """What greetd runs for a session: TVWCS's start-session script, which starts X first for an X session."""
    desktop=re.sub(r"[^A-Za-z0-9_.:-]","",session.get("desktop") or "") or "-"
    return [f"{GREETER_LIB}/start-session",session["kind"],desktop,*session["exec"]]

def default_session(available, wm=""):
    """The session to start when nobody chose one: TVWCS's own session for `wm` (i3 or sway), else that window
    manager, else TVWCS's i3 session, i3, TVWCS's sway session, sway, else the first one."""
    ids=[s["id"] for s in available]
    for sid in ([f"tvwcs-{wm}",wm] if wm else [])+["tvwcs-i3","i3","tvwcs-sway","sway"]:
        if sid in ids: return sid
    return ids[0] if ids else ""

START_SESSION="""#!/bin/sh
# TVWCS's login screen starts sessions with this: start-session <x11|wayland> <desktop name> <command...>.
# Written by TVWCS (loginscreen.py). An X session gets an X server (startx) on this console, through Debian's
# /etc/X11/Xsession when there is one, as other login screens do.
KIND=$1; DESKTOP=$2; shift 2
if [ "$DESKTOP" != - ]; then
    XDG_CURRENT_DESKTOP=$DESKTOP; XDG_SESSION_DESKTOP=$DESKTOP; export XDG_CURRENT_DESKTOP XDG_SESSION_DESKTOP
fi
XDG_SESSION_TYPE=$KIND; export XDG_SESSION_TYPE
if [ "$KIND" = x11 ]; then
    if [ -x /etc/X11/Xsession ]; then exec startx /etc/X11/Xsession "$*"; fi
    exec startx /usr/bin/env "$@"
fi
exec "$@"
"""
GREETER="""#!/bin/sh
# TVWCS's greeter, run by greetd inside cage (see /etc/greetd/config.toml). Written by TVWCS (loginscreen.py).
PYTHONPATH=%(lib)s; PYTHONDONTWRITEBYTECODE=1; export PYTHONPATH PYTHONDONTWRITEBYTECODE
exec python3 -m tvwcs.ui_greeter "$@"
"""

def greeter_command() -> str:
    """greetd's command for the greeter: cage, full screen, with VT switching allowed and no window decorations."""
    return f"cage -s -d -- {GREETER_LIB}/greeter"

def write_greetd_config(user, autologin=None, vt=GREETD_VT) -> str:
    """greetd's config for TVWCS's login screen. autologin: (user, session) for the initial session, which logs that
    user in at start-up (the login screen then shows after logging out)."""
    lines=["# Written by TVWCS (Settings > Features > Login screen). Turning that off puts back the config from before.",
           "[terminal]",f"vt = {vt}","","[default_session]",f"command = {json.dumps(greeter_command())}",f"user = {json.dumps(user)}"]
    if autologin:
        who,session=autologin
        lines+=["","[initial_session]",f"command = {json.dumps(shlex.join(start_session_argv(session)))}",f"user = {json.dumps(who)}"]
    return "\n".join(lines)+"\n"

def autologin() -> tuple:
    """(user, session id) logged in automatically at start-up by the login screen in use, or ("", "")."""
    cur=current()
    if cur=="tvwcs":
        init=greetd_config().get("initial_session",{})
        who=init.get("user",""); cmd=str(init.get("command",""))
        try: argv=shlex.split(cmd)
        except ValueError: argv=[]
        sid=""
        if len(argv)>=3:
            for s in sessions():
                if s["exec"]==argv[3:]: sid=s["id"]; break
        return (who,sid) if who else ("","")
    if cur=="lightdm":
        user=session=""
        files=[path("/etc/lightdm/lightdm.conf")]+sorted(path("/etc/lightdm/lightdm.conf.d").glob("*.conf")) if path("/etc/lightdm").exists() else []
        for f in files:   # later files win, as in LightDM
            try: text=f.read_text(encoding="utf-8")
            except OSError: continue
            section=""
            for line in text.splitlines():
                line=line.strip()
                if line.startswith("["): section=line; continue
                if section.startswith("[Seat:") or section=="[SeatDefaults]":
                    m=re.fullmatch(r"autologin-user\s*=\s*(\S*)",line)
                    if m: user=m.group(1)
                    m=re.fullmatch(r"autologin-session\s*=\s*(\S*)",line)
                    if m: session=m.group(1)
        return (user,session) if user else ("","")
    if cur=="sddm":
        user=session=""
        files=[path("/etc/sddm.conf")]+(sorted(path("/etc/sddm.conf.d").glob("*.conf")) if path("/etc/sddm.conf.d").exists() else [])
        for f in files:
            try: text=f.read_text(encoding="utf-8")
            except OSError: continue
            section=""
            for line in text.splitlines():
                line=line.strip()
                if line.startswith("["): section=line; continue
                if section=="[Autologin]":
                    m=re.fullmatch(r"User\s*=\s*(\S*)",line)
                    if m: user=m.group(1)
                    m=re.fullmatch(r"Session\s*=\s*(\S*)",line)
                    if m: session=m.group(1).removesuffix(".desktop")
        return (user,session) if user else ("","")
    if cur=="":
        m=re.search(r"--autologin\s+(\S+)",_read(GETTY_OVERRIDE))
        return (m.group(1),"") if m else ("","")
    return ("","")

def autologin_supported(unit=None) -> bool:
    return (current() if unit is None else unit) in ("tvwcs","lightdm","sddm","")

# ---------------------------------------------------------------------- the login shell's start lines (no login screen)
# The same lines install.sh writes: after the first console's automatic login, start i3 (startx) or sway there.
START_BEGIN="# >>> TVWCS: start the window manager after the automatic login (added by install.sh; delete to undo) >>>"
START_END="# <<< TVWCS <<<"
def profile_file(home, shell) -> tuple:
    """("sh"|"fish", file) the login shell reads at log-in."""
    home=Path(home); base=os.path.basename(shell or "/bin/sh")
    if base=="fish": return "fish",Path(os.environ.get("XDG_CONFIG_HOME") or home/".config")/"fish"/"conf.d"/"tvwcs-autostart.fish"
    if base=="zsh": return "sh",Path(os.environ.get("ZDOTDIR") or home)/".zprofile"
    if base=="bash":
        for f in (home/".bash_profile",home/".bash_login"):
            if f.exists(): return "sh",f
    return "sh",home/".profile"

def start_block(wm, kind) -> str:
    run,need=("startx","startx") if wm=="i3" else ("sway","sway")
    if kind=="fish":
        body=[f'if status is-login; and test -z "$DISPLAY$WAYLAND_DISPLAY"; and test (tty) = /dev/tty1; and command -q {need}',f"    exec {run}","end"]
    else:
        body=[f'if [ -z "${{DISPLAY:-}}${{WAYLAND_DISPLAY:-}}" ] && [ "$(tty)" = /dev/tty1 ] && command -v {need} >/dev/null 2>&1; then',f"    exec {run}","fi"]
    return "\n".join([START_BEGIN,*body,START_END])+"\n"

def _without_block(text):
    out=[]; skip=False
    for line in text.splitlines(keepends=True):
        if line.rstrip("\n")==START_BEGIN: skip=True
        if not skip: out.append(line)
        if line.rstrip("\n")==START_END: skip=False
    return "".join(out)

def set_start_lines(wm, home=None, shell=None) -> str:
    """Add (wm: i3 or sway) or remove (wm "") the start lines in this user's login shell profile, as this user.
    Returns what was done, for people."""
    me=pwd.getpwuid(os.getuid()); home=Path(home or me.pw_dir); shell=shell or me.pw_shell
    kind,f=profile_file(home,shell)
    try: text=f.read_text(encoding="utf-8")
    except OSError: text=""
    if not wm:
        if START_BEGIN not in text: return ""
        f.write_text(_without_block(text),encoding="utf-8"); return f"Removed the lines that started the session from {f}."
    rest=_without_block(text)
    f.parent.mkdir(parents=True,exist_ok=True)
    f.write_text(rest+("\n" if rest and not rest.endswith("\n\n") else "")+start_block(wm,kind),encoding="utf-8")
    if wm=="i3":
        xinitrc=home/".xinitrc"
        if not xinitrc.exists():
            xinitrc.write_text('#!/bin/sh\n# Written by TVWCS: startx starts i3.\nexport XDG_CURRENT_DESKTOP="${XDG_CURRENT_DESKTOP:-i3}"\n'
                               'command -v dbus-update-activation-environment >/dev/null 2>&1 && dbus-update-activation-environment --systemd DISPLAY XAUTHORITY XDG_CURRENT_DESKTOP\nexec i3\n',encoding="utf-8")
    return f"Added the lines that start {wm} on the first console to {f}."

# ---------------------------------------------------------------------- changing the system (as root)
class Changer:
    """The system changes, done as root by `python3 -m tvwcs.loginscreen`. `run` runs systemctl (not run at all under
    TVWCS_ROOT, where it only records)."""
    def __init__(self, run=None, out=print):
        self.calls=[]; self.out=out
        self._run=run or (None if os.environ.get("TVWCS_ROOT") else (lambda argv:subprocess.run(argv,check=False).returncode))
    def systemctl(self, *args):
        self.calls.append(["systemctl",*args])
        return 0 if self._run is None else self._run(["systemctl",*args])
    def write(self, p, text, mode=0o644):
        f=path(p); f.parent.mkdir(parents=True,exist_ok=True)
        tmp=f.with_name(f.name+".tvwcs-new"); tmp.write_text(text,encoding="utf-8"); os.chmod(tmp,mode); os.replace(tmp,f)
    def remove(self, p):
        try: path(p).unlink(); return True
        except FileNotFoundError: return False

    def install_files(self, source=None, version=""):
        """Copy TVWCS's package (the one running this) and the two scripts to GREETER_LIB, for the greeter."""
        source=Path(source or Path(__file__).resolve().parent)
        lib=path(GREETER_LIB); new=lib.with_name(lib.name+".tvwcs-new")
        shutil.rmtree(new,ignore_errors=True); (new/"tvwcs").mkdir(parents=True)
        for f in source.glob("*.py"): shutil.copy2(f,new/"tvwcs"/f.name)
        (new/"start-session").write_text(START_SESSION,encoding="utf-8"); (new/"greeter").write_text(GREETER%{"lib":GREETER_LIB},encoding="utf-8")
        os.chmod(new/"start-session",0o755); os.chmod(new/"greeter",0o755)
        (new/"VERSION").write_text((version or _version(source))+"\n",encoding="utf-8")
        for p in new.rglob("*"): os.chmod(p,0o755 if p.is_dir() else (p.stat().st_mode|0o644)&0o755)
        os.chmod(new,0o755)
        old=lib.with_name(lib.name+".tvwcs-old"); shutil.rmtree(old,ignore_errors=True)
        if lib.exists(): os.replace(lib,old)
        os.replace(new,lib); shutil.rmtree(old,ignore_errors=True)
    def write_look(self, settings):
        self.write(LOOK,json.dumps(look_from(settings),indent=1)+"\n")
    def state_dir(self, user):
        d=path(STATE_DIR); d.mkdir(parents=True,exist_ok=True); os.chmod(d,0o700)
        if not os.environ.get("TVWCS_ROOT"):
            try: e=pwd.getpwnam(user); os.chown(d,e.pw_uid,e.pw_gid)
            except (KeyError,OSError): pass

    def switch_to(self, unit):
        """Make `unit` the login screen at the next start ("" for none): the old one is disabled, never stopped."""
        old=active_unit()
        if old and old!=unit: self.systemctl("disable",f"{old}.service")
        link=path("/etc/systemd/system/display-manager.service")
        if os.environ.get("TVWCS_ROOT"):   # what systemctl enable / disable would do to the alias
            if link.is_symlink(): link.unlink()
            if unit: link.parent.mkdir(parents=True,exist_ok=True); link.symlink_to(f"/lib/systemd/system/{unit}.service")
        if unit:
            self.systemctl("enable","--force",f"{unit}.service")
            exe=shutil.which(unit,path="/usr/sbin:/usr/bin:/sbin:/bin") or f"/usr/sbin/{unit}"
            self.write("/etc/X11/default-display-manager",exe+"\n")
        else: self.remove("/etc/X11/default-display-manager")
        if unit: self.systemctl("set-default","graphical.target")   # greetd is only started by graphical.target

    def enable(self, settings, version="", source=None, autologin_to=None, before=None):
        """Turn TVWCS's login screen on: copy it, write greetd's config (keeping greetd's old one), remember the login
        screen in use and switch to greetd. autologin_to: (user, session id) to log in at start-up, or None. before: the
        login screen in use before greetd was installed (installing greetd makes it the login screen when there was none)."""
        cur=current() if before is None else before
        cfg=greetd_config(); user=GREETD_USER
        if cfg.get("default_session",{}).get("user") and not greetd_is_ours(cfg): user=cfg["default_session"]["user"]
        elif greetd_is_ours(cfg): user=cfg.get("default_session",{}).get("user",user)
        self.install_files(source,version); self.write_look(settings); self.state_dir(user)
        if cur=="greetd" and path(GREETD_CONF).exists() and not greetd_is_ours(cfg) and not path(GREETD_BACKUP).exists():
            shutil.copy2(path(GREETD_CONF),path(GREETD_BACKUP))
        if cur!="tvwcs": self.write(PREVIOUS,(cur or "")+"\n")
        self.write(GREETD_CONF,write_greetd_config(user,_autologin_pair(autologin_to)))
        if self._getty_is_tvwcs(): self.remove(GETTY_OVERRIDE); self.systemctl("daemon-reload")
        self.switch_to("greetd")
        self.out(f"TVWCS's login screen shows from the next start{' (after '+name(cur)+')' if cur and cur!='tvwcs' else ''}.")

    def update(self, settings, version="", source=None):
        """Bring TVWCS's copy and look up to date (the login screen stays as it is)."""
        self.install_files(source,version); self.write_look(settings); self.out("Updated TVWCS's login screen.")

    def disable(self, to, autologin_to=None):
        """Turn TVWCS's login screen off. to: a login screen's unit (the previous one, or one just installed), or "" for
        none, which logs autologin_to's user in on the first console instead (their start lines are written by them)."""
        if path(GREETD_BACKUP).exists(): os.replace(path(GREETD_BACKUP),path(GREETD_CONF))
        elif greetd_is_ours(): self.remove(GREETD_CONF)
        self.switch_to(to)
        if not to and autologin_to: self.set_getty(autologin_to[0])
        for p in (LOOK,PREVIOUS): self.remove(p)
        shutil.rmtree(path(GREETER_LIB),ignore_errors=True)
        if to and autologin_to: self.set_autologin(autologin_to[0],autologin_to[1],to)
        self.out(f"From the next start, the computer uses {name(to)}." if to else "From the next start, the computer has no login screen.")

    def _getty_is_tvwcs(self):
        return "TVWCS" in _read(GETTY_OVERRIDE)
    def set_getty(self, user):
        agetty=shutil.which("agetty") or "/sbin/agetty"
        self.write(GETTY_OVERRIDE,"\n".join(["# Written by TVWCS: logs "+user+" in on the first console at boot. Delete this file to undo it.",
                   "[Service]","ExecStart=",f"ExecStart=-{agetty} -o '-p -f -- \\\\u' --noclear --autologin {user} %I $TERM"])+"\n")
        self.systemctl("daemon-reload")

    def set_autologin(self, user, session, unit=None):
        """Log `user` in automatically at start-up into `session` (an id from sessions()), or stop it (user "")."""
        unit=current() if unit is None else unit
        if unit=="tvwcs":
            cfg=greetd_config(); greeter_user=cfg.get("default_session",{}).get("user",GREETD_USER)
            vt=cfg.get("terminal",{}).get("vt",GREETD_VT)
            self.write(GREETD_CONF,write_greetd_config(greeter_user,_autologin_pair((user,session)) if user else None,vt if isinstance(vt,int) else GREETD_VT))
        elif unit=="lightdm":
            if user: self.write(LIGHTDM_AUTOLOGIN,"# Written by TVWCS (Settings > User).\n[Seat:*]\n"
                                f"autologin-user={user}\n"+(f"autologin-session={session}\n" if session else ""))
            else:
                self.remove(LIGHTDM_AUTOLOGIN)
                if autologin()[0]: raise SystemExit("LightDM's own settings log someone in automatically; change it in /etc/lightdm.")
        elif unit=="sddm":
            if user: self.write(SDDM_AUTOLOGIN,"# Written by TVWCS (Settings > User).\n[Autologin]\n"
                                f"User={user}\n"+(f"Session={session}.desktop\n" if session else ""))
            else:
                self.remove(SDDM_AUTOLOGIN)
                if autologin()[0]: raise SystemExit("SDDM's own settings log someone in automatically; change it in /etc/sddm.conf.")
        elif unit=="":
            if user: self.set_getty(user)
            elif self.remove(GETTY_OVERRIDE): self.systemctl("daemon-reload")
        else: raise SystemExit(f"TVWCS cannot change the automatic login of {name(unit)}; use its own settings.")
        self.out((f"From the next start, {user} is logged in automatically." if user else "From the next start, nobody is logged in automatically."))

def _autologin_pair(pair):
    """(user, session id) -> (user, session dict) for greetd's initial session, or None."""
    if not pair or not pair[0]: return None
    user,sid=pair; found=sessions()
    s=next((x for x in found if x["id"]==sid),None) or next((x for x in found if x["id"]==default_session(found)),None)
    if s is None: raise SystemExit("There is no i3 or sway session to log in to (no .desktop file in /usr/share/xsessions or wayland-sessions).")
    return user,s

INSTALL_THEN="""set -e
n=$1; shift; packages=""
while [ "$n" -gt 0 ]; do packages="$packages $1"; shift; n=$((n-1)); done
if [ -n "$packages" ]; then apt-get update -q; DEBIAN_FRONTEND=noninteractive apt-get install -y $packages; fi
exec "$@"
"""
def root_command(args, packages=()) -> list:
    """The command (for sudo) that installs `packages` with apt, then runs `python3 -m tvwcs.loginscreen args` from this
    copy of TVWCS. No bytecode is written: root's .pyc files in the user's own TVWCS folder could not be replaced."""
    run=["env","PYTHONDONTWRITEBYTECODE=1",f"PYTHONPATH={Path(__file__).resolve().parent.parent}","python3","-m","tvwcs.loginscreen",*args]
    if not packages: return run
    if not all(re.fullmatch(r"[a-z0-9][a-z0-9+.-]*",p) for p in packages): raise ValueError("Unexpected package name.")
    return ["sh","-c",INSTALL_THEN,"sh",str(len(packages)),*packages,*run]

def tvwcs_session(available, wm, setup=""):
    """The session that starts TVWCS with `wm`: TVWCS's own one (set up next to other desktops), else plain i3 / sway
    (whose config includes TVWCS, set up for TVWCS only)."""
    ids=[s["id"] for s in available]
    order=[wm,f"tvwcs-{wm}"] if setup=="dedicated" else [f"tvwcs-{wm}",wm]
    return next((i for i in order if i in ids),default_session(available,wm))

def _version(source):
    for f in (Path(source).parent/"VERSION",Path(source).parent.parent/"VERSION"):
        try: return f.read_text().strip()
        except OSError: pass
    return ""

def _settings(config_file):
    try: return (json.loads(Path(config_file).read_text(encoding="utf-8")).get("settings") or {}) if config_file else {}
    except (OSError,ValueError,AttributeError): return {}

USAGE="""Usage (as root): python3 -m tvwcs.loginscreen <command>
  enable [--config FILE] [--autologin USER SESSION] [--previous UNIT]
                                                     turn TVWCS's login screen on (from the next start)
  update [--config FILE]                             update its copy of TVWCS and its look (from FILE: a config.json)
  disable [--to UNIT] [--autologin USER SESSION]     turn it off: back to UNIT (default: the one before), or none ("")
  autologin USER SESSION | autologin --off           log USER in at start-up into SESSION (an id: i3, tvwcs-sway...)
  switch UNIT                                        use another installed login screen (sddm...) from the next start
Without root: status, sessions"""

def main(argv):
    args=list(argv)
    def opt(flag, n=1):
        if flag not in args: return None
        i=args.index(flag); vals=args[i+1:i+1+n]
        if len(vals)<n: raise SystemExit(USAGE)
        del args[i:i+1+n]; return vals if n>1 else vals[0]
    if not args: print(USAGE,file=sys.stderr); return 2
    cmd=args.pop(0)
    if cmd=="status": print(json.dumps(status(),indent=1)); return 0
    if cmd=="sessions":
        for s in sessions(): print(f"{s['id']}\t{s['kind']}\t{s['name']}")
        return 0
    if os.geteuid()!=0 and not os.environ.get("TVWCS_ROOT"): print("This needs root.",file=sys.stderr); return 1
    c=Changer(); config=opt("--config"); auto=opt("--autologin",2)
    try:
        if cmd=="enable":
            before=opt("--previous"); c.enable(_settings(config),autologin_to=tuple(auto) if auto else None,before=before)
        elif cmd=="update": c.update(_settings(config))
        elif cmd=="disable":
            to=opt("--to"); c.disable(fallback() if to is None else to,tuple(auto) if auto else None)
        elif cmd=="switch" and len(args)==1: c.switch_to(args[0]); c.out(f"From the next start, the computer uses {name(args[0])}.")
        elif cmd=="autologin":
            if args==["--off"]: c.set_autologin("","")
            elif len(args)==2: c.set_autologin(args[0],args[1])
            else: print(USAGE,file=sys.stderr); return 2
        else: print(USAGE,file=sys.stderr); return 2
    except SystemExit as exc:
        if isinstance(exc.code,str): print(exc.code,file=sys.stderr); return 1
        raise
    return 0

if __name__=="__main__": sys.exit(main(sys.argv[1:]))
