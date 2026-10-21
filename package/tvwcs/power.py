"""Power and sleep: turning the screen off, locking and sleeping after a time without input. No GTK dependency.

The times are TVWCS options ("idle" in config.json), set on the Settings app's Power and sleep page. TVWCS itself
keeps them, because neither i3 nor sway has an idle manager of its own:
- On X11 (i3) TVWCS reads how long the keyboard, mouse and remote have been untouched (the XScreenSaver extension
  through libXss, else `xprintidle`) and acts when a time is reached. X's own screen saver and DPMS timers are
  switched off while TVWCS turns the screen off, so the two never fight.
- On sway it runs `swayidle` with the same times; swayidle calls `tvwcs idle <action>` back.
Nothing happens while sound is playing (a film with no one touching the remote), or while an application holds an
idle inhibitor (systemd-inhibit --what=idle).

Also read, to show what the system does on its own: X's screen saver and DPMS times (`xset q`) and logind's idle
action and lid switch handling."""
from __future__ import annotations
import ctypes, ctypes.util, os, re, shutil, subprocess
from dataclasses import dataclass, field

from tvwcs.control_cmd import have, key_values, run

ACTIONS=("screensaver","screen_off","lock","sleep")
LABELS={"screensaver":"Screen saver after","screen_off":"Turn off the screen after","lock":"Lock after","sleep":"Sleep after"}
CHOICES=(0,60,120,300,600,900,1200,1800,2700,3600,7200)   # seconds; 0 is Never

def duration_text(seconds):
    if not seconds: return "Never"
    if seconds<60: return f"{seconds} seconds"
    minutes=seconds//60
    if minutes<60 or minutes%60: return f"{minutes} minute{'s' if minutes!=1 else ''}"
    hours=minutes//60; return f"{hours} hour{'s' if hours!=1 else ''}"

def clean_idle(raw):
    """The "idle" option: {"screen_off": seconds, 0 (Never) or None, "lock": seconds or 0, "sleep": ...}. A screen_off of
    None leaves the screen to the system (X's own blanking and DPMS); unknown values become that, or Never."""
    out={"screensaver":0,"screen_off":None,"lock":0,"sleep":0}
    if isinstance(raw,dict):
        for a in ACTIONS:
            v=raw.get(a)
            if isinstance(v,int) and not isinstance(v,bool) and 0<=v<=86400: out[a]=v
    return out

def due(settings, idle_seconds, done):
    """The actions whose time has come and that have not run in this idle period, in the order they should run."""
    order=sorted((a for a in ACTIONS if settings.get(a)),key=lambda a:(settings[a],ACTIONS.index(a)))
    return [a for a in order if idle_seconds>=settings[a] and a not in done]

# ---------------------------------------------------------------------- battery
# A computer with a battery has a second set of times for when it runs on the battery ("idle_battery"), and an action
# for when the battery is nearly empty ("battery_critical"). A desktop has neither, and the page does not show them.
CRITICAL_ACTIONS={"nothing":"Nothing","sleep":"Sleep","shutdown":"Shut down"}
CRITICAL_PERCENTS=(2,3,5,7,10,15)
POWER_SUPPLY="/sys/class/power_supply"

def clean_critical(raw):
    """The "battery_critical" option: {"action": a CRITICAL_ACTIONS key, "percent": 1-50}. Shut down at 5% unless set."""
    out={"action":"shutdown","percent":5}
    if isinstance(raw,dict):
        if raw.get("action") in CRITICAL_ACTIONS: out["action"]=raw["action"]
        p=raw.get("percent")
        if isinstance(p,int) and not isinstance(p,bool) and 1<=p<=50: out["percent"]=p
    return out

@dataclass
class Battery:
    present: bool = False      # the computer runs on a battery of its own (not a mouse's or a phone's)
    percent: int = 100
    on_battery: bool = False   # not plugged in
    charging: bool = False     # plugged in and charging (plugged in and not charging: full, or held below full)

def read_battery(root=None):
    """The computer's batteries in /sys/class/power_supply (a mouse's or headset's, scope "Device", are left out) and
    whether the charger is plugged in. Several batteries count as one."""
    def value(path, name):
        try:
            with open(os.path.join(path,name),encoding="utf-8") as f: return f.read().strip()
        except OSError: return ""
    try: entries=sorted(os.scandir(root or POWER_SUPPLY),key=lambda e:e.name)
    except OSError: return Battery()
    now=full=0; percents=[]; discharging=charging=False; mains=None
    for e in entries:
        kind=value(e.path,"type")
        if kind=="Mains" or (kind.startswith("USB") and value(e.path,"online")):
            if value(e.path,"online")=="1": mains=True
            elif mains is None: mains=False
            continue
        if kind!="Battery" or value(e.path,"scope")=="Device" or value(e.path,"present")=="0": continue
        status=value(e.path,"status")
        if status=="Discharging": discharging=True
        elif status=="Charging": charging=True
        for a,b in (("energy_now","energy_full"),("charge_now","charge_full")):
            n,f=value(e.path,a),value(e.path,b)
            if n.isdigit() and f.isdigit() and int(f)>0: now+=int(n); full+=int(f); break
        else:
            c=value(e.path,"capacity")
            if c.isdigit(): percents.append(int(c))
    if not full and not percents: return Battery()
    percent=round(100*now/full) if full else round(sum(percents)/len(percents))
    on_battery=discharging or mains is False
    return Battery(True,max(0,min(100,percent)),on_battery,charging and not on_battery)

def active_idle(settings, battery):
    """The times in use now: the battery's while the computer runs on it, else the plugged-in ones."""
    return settings["idle_battery"] if battery.present and battery.on_battery else settings["idle"]

def critical(settings, battery):
    """The action to take now because the battery is nearly empty ("" for none)."""
    c=settings["battery_critical"]
    if not (battery.present and battery.on_battery) or c["action"]=="nothing": return ""
    return c["action"] if battery.percent<=c["percent"] else ""

# ---------------------------------------------------------------------- what the system does by itself
@dataclass
class XTimers:
    available: bool = False
    saver: int = 0             # screen saver (blanking) timeout, seconds; 0 = off
    dpms: bool = False         # DPMS present and enabled
    dpms_off: int = 0          # seconds until the monitor is switched off by DPMS (the smallest non-zero of its three)

def parse_xset(text):
    t=XTimers(available=bool(text.strip()))
    m=re.search(r"timeout:\s*(\d+)",text)
    if m: t.saver=int(m.group(1))
    t.dpms="DPMS is Enabled" in text
    times=[int(x) for x in re.findall(r"(?:Standby|Suspend|Off):\s*(\d+)",text) if int(x)>0]
    t.dpms_off=min(times) if times and t.dpms else 0
    return t

@dataclass
class Logind:
    available: bool = False
    idle_action: str = "ignore"
    idle_seconds: int = 0
    lid: str = ""

def parse_logind(props):
    """`busctl get-property` answers ({name: 's "suspend"' / 't 1800000000'}) -> Logind."""
    def value(name):
        raw=props.get(name,"").split(" ",1)
        return raw[1].strip().strip('"') if len(raw)==2 else ""
    usec=value("IdleActionUSec")
    return Logind(bool(props),value("IdleAction") or "ignore",int(usec)//1_000_000 if usec.isdigit() else 0,value("HandleLidSwitch"))

def read_logind():
    if not have("busctl"): return Logind()
    props={}
    for name in ("IdleAction","IdleActionUSec","HandleLidSwitch"):
        r=run(["busctl","--system","get-property","org.freedesktop.login1","/org/freedesktop/login1","org.freedesktop.login1.Manager",name],timeout=5)
        if r.ok: props[name]=r.out.strip()
    state=parse_logind(props)
    if not has_lid(): state.lid=""   # logind has a lid setting everywhere; only show it where there is a lid
    return state

LID_PATHS=("/proc/acpi/button/lid","/sys/bus/acpi/devices")

def has_lid(paths=LID_PATHS):
    """Whether the computer has a lid switch: an ACPI lid button (LID0, or the PNP0C0D device). A desktop has none."""
    proc,acpi=paths
    try:
        if any(os.scandir(proc)): return True
    except OSError: pass
    try: return any(e.name.startswith("PNP0C0D") for e in os.scandir(acpi))
    except OSError: return False

def read_xset(env=None):
    env=os.environ if env is None else env
    if not env.get("DISPLAY") or not have("xset"): return XTimers()
    r=run(["xset","q"],timeout=5)
    return parse_xset(r.out) if r.ok else XTimers()

def sway(env=None):
    env=os.environ if env is None else env
    return bool(env.get("SWAYSOCK"))

# ---------------------------------------------------------------------- reading idle time, and what keeps it awake
class XIdle:
    """Milliseconds since the last input on X11: libXss when it can be loaded, else xprintidle, else None."""
    def __init__(self):
        self.lib=None; self.display=None; self.info=None
        try:
            x11=ctypes.cdll.LoadLibrary(ctypes.util.find_library("X11") or "libX11.so.6")
            xss=ctypes.cdll.LoadLibrary(ctypes.util.find_library("Xss") or "libXss.so.1")
        except OSError: return
        class Info(ctypes.Structure):
            _fields_=[("window",ctypes.c_ulong),("state",ctypes.c_int),("kind",ctypes.c_int),("til_or_since",ctypes.c_ulong),
                      ("idle",ctypes.c_ulong),("eventMask",ctypes.c_ulong)]
        x11.XOpenDisplay.restype=ctypes.c_void_p; x11.XOpenDisplay.argtypes=[ctypes.c_char_p]
        x11.XDefaultRootWindow.restype=ctypes.c_ulong; x11.XDefaultRootWindow.argtypes=[ctypes.c_void_p]
        xss.XScreenSaverAllocInfo.restype=ctypes.POINTER(Info)
        xss.XScreenSaverQueryInfo.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.POINTER(Info)]
        display=x11.XOpenDisplay(None)
        if not display: return
        self.x11,self.lib,self.display,self.info=x11,xss,display,xss.XScreenSaverAllocInfo()
    def ms(self):
        if self.lib is not None and self.lib.XScreenSaverQueryInfo(self.display,self.x11.XDefaultRootWindow(self.display),self.info):
            return int(self.info.contents.idle)
        if have("xprintidle"):
            r=run(["xprintidle"],timeout=5)
            if r.ok and r.out.strip().isdigit(): return int(r.out.strip())
        return None

def x_idle_available():
    """libXss (or xprintidle) is there to read the idle time, without opening the display."""
    if have("xprintidle"): return True
    try: ctypes.cdll.LoadLibrary(ctypes.util.find_library("Xss") or "libXss.so.1"); return True
    except OSError: return False

def parse_playing(text):
    """`pactl list sink-inputs`: True when a stream is playing (not corked)."""
    return any(line.strip()=="Corked: no" for line in text.splitlines())

def sound_playing():
    if not have("pactl"): return False
    r=run(["pactl","list","sink-inputs"],timeout=5)
    return r.ok and parse_playing(r.out)

def parse_inhibitors(text):
    """`systemd-inhibit --list --no-legend` (WHO UID USER PID COMM WHAT WHY MODE): who blocks idle, by name."""
    who=[]
    for line in text.splitlines():
        parts=line.split()
        if len(parts)>=7 and "idle" in parts[5].split(":") and parts[-1]=="block": who.append(parts[0])
    return who

def idle_blocked():
    if not have("systemd-inhibit"): return []
    r=run(["systemd-inhibit","--list","--no-legend","--no-pager"],timeout=5)
    return parse_inhibitors(r.out) if r.ok else []

def keep_awake():
    """Why nothing should happen now ("" when something may): sound playing, or an idle inhibitor."""
    if sound_playing(): return "sound is playing"
    who=idle_blocked()
    return f"{who[0]} is keeping the computer awake" if who else ""

# ---------------------------------------------------------------------- acting (X11)
X_SAVED_NAME="tvwcs-x-timers"   # X's own times from before TVWCS took over, in the runtime directory

def parse_x_saved(text):
    """`xset q` -> the times to give X back later: "saver standby suspend off dpms" (dpms 1 or 0), or "" when unknown."""
    m=re.search(r"timeout:\s*(\d+)",text); d=[re.search(rf"{k}:\s*(\d+)",text) for k in ("Standby","Suspend","Off")]
    if not m or not all(d): return ""
    return " ".join([m.group(1),*(x.group(1) for x in d),"1" if "DPMS is Enabled" in text else "0"])

def x_restore_argv(saved):
    """The xset command that gives X back the times parse_x_saved kept, or None."""
    parts=saved.split()
    if len(parts)!=5 or not all(p.isdigit() for p in parts): return None
    saver,standby,suspend,off,on=parts
    return ["xset","s",saver,"+dpms" if on=="1" else "-dpms","dpms",standby,suspend,off]

def x_take_over(screen_off_setting, env=None):
    """Unless the screen is left to the system (None), TVWCS turns it off itself: X's own blanking and DPMS timers are
    switched off, and DPMS stays on so TVWCS can switch the monitor off. X's times are kept first, and given back when
    the screen is left to the system again: otherwise a laptop whose plugged-in times have "Turn off the screen after"
    set and whose battery times leave it to the system would never turn its screen off on the battery."""
    if not have("xset"): return
    from tvwcs.session import runtime_dir
    saved=runtime_dir(env)/X_SAVED_NAME
    if screen_off_setting is not None:
        if not saved.exists():   # kept once a login: a TVWCS restart finds X already switched off by the last one
            r=run(["xset","q"],timeout=5); text=parse_x_saved(r.out) if r.ok else ""
            if text:
                try: saved.parent.mkdir(parents=True,exist_ok=True); saved.write_text(text)
                except OSError: pass
        run(["xset","s","off","+dpms","dpms","0","0","0"],timeout=5)
        return
    try: argv=x_restore_argv(saved.read_text())
    except OSError: return   # TVWCS never took over: X has its own times already
    if argv and run(argv,timeout=5).ok:
        try: saved.unlink()
        except OSError: pass

def screen_off(env=None):
    if sway(env): return run(["swaymsg","output * power off"],timeout=5)
    return run(["xset","dpms","force","off"],timeout=5)

def screen_on(env=None):
    if sway(env): return run(["swaymsg","output * power on"],timeout=5)
    return run(["xset","dpms","force","on"],timeout=5)

# ---------------------------------------------------------------------- xss-lock
# Debian's and Ubuntu's i3 config starts `xss-lock -- i3lock`, which locks the screen whenever X's screen saver comes
# on. X turns its screen saver on whenever the monitor is switched off, so with it running, "Turn off the screen
# after" also locks the computer, whatever "Lock after" says, and a TV then wakes up to a password prompt.
_XSS_LINE=re.compile(r"^\s*exec(?:_always)?\s+(?:--no-startup-id\s+)?xss-lock\b")
XSS_NOTE="# Turned off by TVWCS's Settings: xss-lock locked the screen whenever it turned off. Remove the # to use it again."

def xss_lock_running(proc="/proc"):
    try: entries=[e.name for e in os.scandir(proc) if e.name.isdigit()]
    except OSError: return False
    for pid in entries:
        try:
            with open(f"{proc}/{pid}/comm",encoding="utf-8",errors="replace") as f:
                if f.read().strip()=="xss-lock": return True
        except OSError: continue
    return False

def i3_config_path(env=None):
    """The config this i3 runs with, or None. In TVWCS's own session (install.sh's "next to my other desktops" setup)
    that is TVWCS's session config: its tvwcs-session wrapper exports TVWCS_SESSION and the `i3 -c` path in
    TVWCS_SESSION_CONFIG, so a fix made here never touches the user's usual i3 config. Otherwise it is the config i3
    reads first (~/.config/i3/config, else ~/.i3/config)."""
    env=os.environ if env is None else env
    home=env.get("HOME") or os.path.expanduser("~")
    config_home=env.get("XDG_CONFIG_HOME") or os.path.join(home,".config")
    if env.get("TVWCS_SESSION"):
        session=env.get("TVWCS_SESSION_CONFIG") or os.path.join(config_home,"tvwcs","i3-session.conf")
        return session if os.path.isfile(session) else None
    for p in (os.path.join(config_home,"i3","config"),os.path.join(home,".i3","config")):
        if os.path.isfile(p): return p
    return None

def xss_lock_lines(text):
    """The line numbers (from 0) of the config lines that start xss-lock."""
    return [i for i,line in enumerate(text.splitlines()) if _XSS_LINE.match(line)]

def without_xss_lock(text):
    """The config with each xss-lock line commented out, under a note saying why."""
    lines=text.splitlines(keepends=True); found=set(xss_lock_lines(text)); out=[]
    for i,line in enumerate(lines):
        if i in found: out+=[XSS_NOTE+"\n","# "+line]
        else: out.append(line)
    return "".join(out)

def stop_xss_lock(path):
    """Comment xss-lock out of the i3 config (keeping a copy as config.before-tvwcs), then stop the running one.
    Returns "" when it worked, else why not."""
    try: text=open(path,encoding="utf-8").read()
    except OSError as exc: return f"Could not read {path}: {exc.strerror}"
    if xss_lock_lines(text):
        backup=path+".before-tvwcs"
        try:
            if not os.path.exists(backup): shutil.copy2(path,backup)
            tmp=path+".tvwcs-new"
            with open(tmp,"w",encoding="utf-8") as f: f.write(without_xss_lock(text))
            os.replace(tmp,path)
        except OSError as exc: return f"Could not change {path}: {exc.strerror}"
    if have("pkill"): run(["pkill","-x","xss-lock"],timeout=5)
    return ""

XSS_LOCKER_NOTE="# TVWCS lock screen (Settings > Power and sleep). xss-lock ran before: "
def xss_lock_locker(text):
    """The locker command of the first active xss-lock line (after its "--"), or ""."""
    lines=text.splitlines()
    for i in xss_lock_lines(text):
        if " -- " in lines[i]: return lines[i].split(" -- ",1)[1].strip()
    return ""
def with_xss_locker(text, tvwcs_locker):
    """The config with xss-lock running TVWCS's lock screen (`tvwcs_locker`), or, with "", the locker it ran before
    (remembered in a note above the line; i3lock --nofork when the note is gone)."""
    lines=text.splitlines(keepends=True); found=set(xss_lock_lines(text)); out=[]
    for i,line in enumerate(lines):
        if i in found and " -- " in line:
            head,locker=line.rstrip("\n").split(" -- ",1)
            prev=out[-1] if out else ""
            if prev.startswith(XSS_LOCKER_NOTE): before=prev[len(XSS_LOCKER_NOTE):].strip(); out.pop()
            else: before=locker.strip()
            if tvwcs_locker: out+=[XSS_LOCKER_NOTE+before+"\n",f"{head} -- {tvwcs_locker}\n"]
            else: out.append(f"{head} -- {before or 'i3lock --nofork'}\n")
        else: out.append(line)
    return "".join(out)
def use_tvwcs_locker(path, tvwcs_locker):
    """Point the i3 config's xss-lock at TVWCS's lock screen (or back, with ""), then restart xss-lock with the new line.
    Returns "" when it worked, else why not."""
    try: text=open(path,encoding="utf-8").read()
    except OSError as exc: return f"Could not read {path}: {exc.strerror}"
    new=with_xss_locker(text,tvwcs_locker)
    if new==text: return ""
    try:
        backup=path+".before-tvwcs"
        if not os.path.exists(backup): shutil.copy2(path,backup)
        tmp=path+".tvwcs-new"
        with open(tmp,"w",encoding="utf-8") as f: f.write(new)
        os.replace(tmp,path)
    except OSError as exc: return f"Could not change {path}: {exc.strerror}"
    line=new.splitlines()[xss_lock_lines(new)[0]]
    command=re.sub(r"^\s*exec(?:_always)?\s+(?:--no-startup-id\s+)?","",line)
    if xss_lock_running():   # restarted with the new locker; one that is not running starts with it next time i3 starts
        if have("pkill"): run(["pkill","-x","xss-lock"],timeout=5)
        if have("i3-msg"): run(["i3-msg","exec --no-startup-id "+command],timeout=5)
    return ""

# ---------------------------------------------------------------------- sway: swayidle
def swayidle_argv(settings, launcher):
    """swayidle with one timeout per action; each calls `tvwcs idle <action>` back, which checks sound and inhibitors.
    The screen saver is left out: it is a plain fullscreen window, which takes fullscreen away from what had it on sway
    (a layer-shell overlay would be needed), so Settings hides it there for now."""
    argv=["swayidle","-w"]
    for a in ACTIONS:
        if settings.get(a) and a!="screensaver":
            argv+=["timeout",str(settings[a]),f"'{launcher}' idle {a}"]
            if a=="screen_off": argv+=["resume",f"'{launcher}' idle resume"]
    return argv if len(argv)>2 else None

class SwayIdle:
    """The swayidle process TVWCS runs on sway; restarted when the times change."""
    def __init__(self): self.proc=None; self.argv=None
    def apply(self, settings, launcher):
        argv=swayidle_argv(settings,launcher)
        if argv==self.argv and self.proc is not None and self.proc.poll() is None: return ""
        self.stop(); self.argv=argv
        if argv is None: return ""
        if not shutil.which("swayidle"): return "swayidle is not installed, so the Power and sleep times cannot be used on sway."
        try: self.proc=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        except OSError as exc: return f"Could not start swayidle: {exc}"
        return ""
    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try: self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired: self.proc.kill()
        self.proc=None

@dataclass
class PowerState:
    """What the Power and sleep page shows."""
    settings: dict = field(default_factory=dict)
    session: str = "X11"           # "X11" or "sway"
    xtimers: XTimers = field(default_factory=XTimers)
    logind: Logind = field(default_factory=Logind)
    idle_works: bool = True        # TVWCS can tell how long the computer has been idle here
    locker: bool = True            # a screen locker is installed
    can_sleep: bool = True
    xss_lock: str = ""             # X11: xss-lock is running; the i3 config line that starts it ("?" when not found there)
    battery: Battery = field(default_factory=Battery)
    battery_settings: dict = field(default_factory=dict)
    critical: dict = field(default_factory=dict)

def read_state(settings, lock_ok, sleep_ok):
    on_sway=sway()
    works=bool(shutil.which("swayidle")) if on_sway else x_idle_available()
    xss=""
    if not on_sway and xss_lock_running():
        path=i3_config_path(); xss="?"
        if path:
            try: xss=path if xss_lock_lines(open(path,encoding="utf-8").read()) else "?"
            except OSError: pass
    return PowerState(clean_idle(settings.get("idle")),"sway" if on_sway else "X11",XTimers() if on_sway else read_xset(),
                      read_logind(),works,lock_ok,sleep_ok,xss,read_battery(),clean_idle(settings.get("idle_battery")),
                      clean_critical(settings.get("battery_critical")))
