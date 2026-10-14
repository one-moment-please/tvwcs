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

ACTIONS=("screen_off","lock","sleep")
LABELS={"screen_off":"Turn off the screen after","lock":"Lock after","sleep":"Sleep after"}
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
    out={"screen_off":None,"lock":0,"sleep":0}
    if isinstance(raw,dict):
        for a in ACTIONS:
            v=raw.get(a)
            if isinstance(v,int) and not isinstance(v,bool) and 0<=v<=86400: out[a]=v
    return out

def due(settings, idle_seconds, done):
    """The actions whose time has come and that have not run in this idle period, in the order they should run."""
    order=sorted((a for a in ACTIONS if settings.get(a)),key=lambda a:(settings[a],ACTIONS.index(a)))
    return [a for a in order if idle_seconds>=settings[a] and a not in done]

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
    return parse_logind(props)

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
def x_take_over(screen_off_setting):
    """Unless the screen is left to the system (None), TVWCS turns it off itself: X's own blanking and DPMS timers are
    switched off, and DPMS stays on so TVWCS can switch the monitor off."""
    if screen_off_setting is not None and have("xset"): run(["xset","s","off","+dpms","dpms","0","0","0"],timeout=5)

def screen_off(env=None):
    if sway(env): return run(["swaymsg","output * power off"],timeout=5)
    return run(["xset","dpms","force","off"],timeout=5)

def screen_on(env=None):
    if sway(env): return run(["swaymsg","output * power on"],timeout=5)
    return run(["xset","dpms","force","on"],timeout=5)

# ---------------------------------------------------------------------- sway: swayidle
def swayidle_argv(settings, launcher):
    """swayidle with one timeout per action; each calls `tvwcs idle <action>` back, which checks sound and inhibitors."""
    argv=["swayidle","-w"]
    for a in ACTIONS:
        if settings.get(a):
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

def read_state(settings, lock_ok, sleep_ok):
    on_sway=sway()
    works=bool(shutil.which("swayidle")) if on_sway else x_idle_available()
    return PowerState(clean_idle(settings.get("idle")),"sway" if on_sway else "X11",XTimers() if on_sway else read_xset(),
                      read_logind(),works,lock_ok,sleep_ok)
