"""Hiding the mouse pointer in TV mode. No GTK dependency.

In TV mode (a TVWCS session) the pointer is hidden after 3 seconds without moving and comes back as soon as it moves;
in desktop mode TVWCS leaves it alone. TVWCS does this itself: on sway with `seat * hide_cursor`, on X11 (i3) with
unclutter.

A hidden pointer still rests over something, and applications keep showing that hover (a highlighted button, a
tooltip). sway takes the pointer's focus away when it hides it. On X11 TVWCS moves the hidden pointer out of the way
instead: to the bottom-right corner of the focused window, where there is rarely anything to highlight. TVWCS's own
windows also stop showing hover then (widgets.PointerWatch).

Only TVWCS's own session is affected: the unclutter TVWCS starts ends with TVWCS (the kernel stops it when TVWCS
exits, however it exits), so it never outlives the i3 session. Debian's unclutter-startup package, which apt brings in
with unclutter-xfixes, would start unclutter in every X session (GNOME, Cinnamon, ...); install.sh leaves it out, and
turns its autostart off (/etc/default/unclutter) when asked."""
from __future__ import annotations
import ctypes, ctypes.util, os, shutil, subprocess

DEFAULT_SECONDS=3

def hide_enabled(settings=None, env=None, which=shutil.which):
    """On in TV mode only; on X11 it needs unclutter."""
    from tvwcs.model import tv_mode
    if not tv_mode(env): return False
    return sway(env) or bool(which("unclutter"))

def hide_seconds(settings=None): return DEFAULT_SECONDS

def hide_ms(settings):
    """The hiding time in ms, or None when the pointer is never hidden."""
    return hide_seconds(settings)*1000 if hide_enabled(settings) else None

def sway(env=None):
    env=os.environ if env is None else env
    return bool(env.get("SWAYSOCK"))

def sway_command(enabled, seconds):
    return f"seat * hide_cursor {seconds*1000 if enabled else 0}"

def unclutter_argv(seconds):
    return ["unclutter","-idle",str(seconds)]   # unclutter-xfixes reads the old unclutter's -idle too

PR_SET_PDEATHSIG=1
def _end_with_parent():
    """Run in the child before unclutter starts (Linux): it gets SIGTERM when TVWCS exits."""
    import signal
    try:
        libc=ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6",use_errno=True)
        libc.prctl(PR_SET_PDEATHSIG,signal.SIGTERM,0,0,0)
    except (OSError,AttributeError): pass

def corner(rect, inset=2):
    """Where the hidden pointer is put: just inside the bottom-right corner of `rect` (an i3 rect)."""
    return int(rect["x"]+rect["width"]-inset),int(rect["y"]+rect["height"]-inset)

class XPointer:
    """Reads and moves the X pointer through Xlib (no command run each time)."""
    def __init__(self):
        self.x11=None; self.dpy=None
        try: x11=ctypes.cdll.LoadLibrary(ctypes.util.find_library("X11") or "libX11.so.6")
        except OSError: return
        x11.XOpenDisplay.restype=ctypes.c_void_p; x11.XOpenDisplay.argtypes=[ctypes.c_char_p]
        x11.XDefaultRootWindow.restype=ctypes.c_ulong; x11.XDefaultRootWindow.argtypes=[ctypes.c_void_p]
        ul,i,u=ctypes.POINTER(ctypes.c_ulong),ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_uint)
        x11.XQueryPointer.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ul,ul,i,i,i,i,u]
        x11.XWarpPointer.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_int,ctypes.c_int,ctypes.c_uint,ctypes.c_uint,ctypes.c_int,ctypes.c_int]
        x11.XFlush.argtypes=[ctypes.c_void_p]
        dpy=x11.XOpenDisplay(None)
        if dpy: self.x11,self.dpy=x11,dpy; self.root=x11.XDefaultRootWindow(dpy)
    def position(self):
        if not self.dpy: return None
        r,c=ctypes.c_ulong(),ctypes.c_ulong(); rx,ry,wx,wy=(ctypes.c_int() for _ in range(4)); mask=ctypes.c_uint()
        if not self.x11.XQueryPointer(self.dpy,self.root,ctypes.byref(r),ctypes.byref(c),ctypes.byref(rx),ctypes.byref(ry),
                                      ctypes.byref(wx),ctypes.byref(wy),ctypes.byref(mask)): return None
        return rx.value,ry.value
    def move(self, x, y):
        if self.dpy: self.x11.XWarpPointer(self.dpy,0,self.root,0,0,0,0,int(x),int(y)); self.x11.XFlush(self.dpy)

class Parker:
    """Counts how long the X pointer has rested; once it has rested for the hiding time, `due` says to move it.
    Moved once per rest: it is not moved again until someone moves it."""
    def __init__(self): self.last=None; self.still=0.0; self.parked=None
    def tick(self, position, elapsed, seconds):
        """-> True when the pointer should be put out of the way now."""
        if position is None: return False
        if position!=self.last: self.last=position; self.still=0.0; return False
        self.still+=elapsed
        return self.still>=seconds and position!=self.parked
    def moved_to(self, position): self.parked=position; self.last=position

class CursorHider:
    """Starts and stops what hides the pointer, as the options say."""
    def __init__(self, run=subprocess.run, popen=subprocess.Popen, which=shutil.which):
        self.run,self.popen,self.which=run,popen,which; self.proc=None; self.applied=None
    def apply(self, settings, env=None):
        on,seconds=hide_enabled(settings,env,lambda n:True),hide_seconds(settings)
        if (on,seconds)==self.applied and (not on or sway(env) or (self.proc is not None and self.proc.poll() is None)): return ""
        self.applied=(on,seconds)
        if sway(env):
            try: self.run(["swaymsg",sway_command(on,seconds)],capture_output=True,timeout=3)
            except (OSError,subprocess.SubprocessError): pass
            return ""
        self.stop()
        if not on: return ""   # desktop mode: the pointer is left as the session has it
        # an unclutter started by an older tvwcs.conf (or by hand) would keep hiding the pointer on its own timing
        if self.which("pkill"):
            try: self.run(["pkill","-u",str(os.getuid()),"-x","unclutter"],capture_output=True,timeout=3)
            except (OSError,subprocess.SubprocessError): pass
        if not self.which("unclutter"): return "unclutter is not installed, so the mouse pointer cannot be hidden. Install unclutter-xfixes."
        try: self.proc=self.popen(unclutter_argv(seconds),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                  start_new_session=True,preexec_fn=_end_with_parent)
        except OSError as exc: return f"Could not start unclutter: {exc}"
        return ""
    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try: self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired: self.proc.kill()
        self.proc=None
