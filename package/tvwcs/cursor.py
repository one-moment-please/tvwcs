"""Hiding the mouse pointer (Settings > Options > Hide the mouse pointer). No GTK dependency.

The pointer is hidden after a few seconds without moving and comes back as soon as it moves. TVWCS does this itself
(it used to be a line in tvwcs.conf): on sway with `seat * hide_cursor`, on X11 (i3) with unclutter. By default it is
on in TV mode (3 seconds) and off at a desk.

A hidden pointer still rests over something, and applications keep showing that hover (a highlighted button, a
tooltip). sway takes the pointer's focus away when it hides it. On X11 TVWCS moves the hidden pointer out of the way
instead: to the bottom-right corner of the focused window, where there is rarely anything to highlight. TVWCS's own
windows also stop showing hover then (widgets.PointerWatch)."""
from __future__ import annotations
import ctypes, ctypes.util, os, shutil, subprocess

DEFAULT_SECONDS=3
SECONDS_RANGE=(1,60)

def hide_enabled(settings):
    """cursor_hide None follows the use: on for a TV, off at a desk."""
    v=settings.get("cursor_hide")
    return settings.get("use")=="tv" if v is None else bool(v)

def hide_seconds(settings):
    v=settings.get("cursor_hide_seconds",DEFAULT_SECONDS)
    lo,hi=SECONDS_RANGE
    return v if isinstance(v,int) and not isinstance(v,bool) and lo<=v<=hi else DEFAULT_SECONDS

def hide_ms(settings):
    """The hiding time in ms, or None when the pointer is never hidden."""
    return hide_seconds(settings)*1000 if hide_enabled(settings) else None

def clamp_seconds(v):
    lo,hi=SECONDS_RANGE
    return max(lo,min(hi,int(v)))

def sway(env=None):
    env=os.environ if env is None else env
    return bool(env.get("SWAYSOCK"))

def sway_command(enabled, seconds):
    return f"seat * hide_cursor {seconds*1000 if enabled else 0}"

def unclutter_argv(seconds):
    return ["unclutter","-idle",str(seconds)]   # unclutter-xfixes reads the old unclutter's -idle too

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
        on,seconds=hide_enabled(settings),hide_seconds(settings)
        if (on,seconds)==self.applied and (not on or sway(env) or (self.proc is not None and self.proc.poll() is None)): return ""
        self.applied=(on,seconds)
        if sway(env):
            try: self.run(["swaymsg",sway_command(on,seconds)],capture_output=True,timeout=3)
            except (OSError,subprocess.SubprocessError): pass
            return ""
        self.stop()
        # an unclutter started by an older tvwcs.conf (or by hand) would keep hiding the pointer on its own timing
        if self.which("pkill"):
            try: self.run(["pkill","-u",str(os.getuid()),"-x","unclutter"],capture_output=True,timeout=3)
            except (OSError,subprocess.SubprocessError): pass
        if not on: return ""
        if not self.which("unclutter"): return "unclutter is not installed, so the mouse pointer cannot be hidden. Install unclutter-xfixes."
        try: self.proc=self.popen(unclutter_argv(seconds),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        except OSError as exc: return f"Could not start unclutter: {exc}"
        return ""
    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try: self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired: self.proc.kill()
        self.proc=None
