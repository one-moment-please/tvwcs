"""TVWCS's screen saver (Settings > Power and sleep > Screen saver): a logo drifting across a black screen, bouncing off
the edges and changing colour at each bounce, like a DVD player left alone. `tvwcs screensaver` shows it until a key,
the remote, a click or a mouse movement; TVWCS starts it after the "Screen saver after" time (on sway, swayidle does).

The logo is the DVD Video logo, TVWCS's own in the same style, or a picture the user chose. The movement has no GTK
dependency (step, logo_size) and is unit-tested; the window is GTK and is only imported when it runs."""
from __future__ import annotations
import os, random, signal, sys

from tvwcs.session import runtime_dir

SPEED=2.2               # pixels per frame at 1080p
FRAME_MS=16
COLOURS=("#ffffff","#e81123","#ff8c00","#ffd800","#00cc6a","#00b7c3","#0078d7","#b146c2","#ea005e")
PID_NAME="tvwcs-screensaver.pid"

def step(x, y, dx, dy, w, h, width, height):
    """One frame: move the logo (w x h at x, y) by dx, dy inside width x height, bouncing off the edges.
    -> (x, y, dx, dy, bounced)."""
    x+=dx; y+=dy; bounced=False
    if x<=0: x=0; dx=abs(dx); bounced=True
    elif x+w>=width: x=max(0,width-w); dx=-abs(dx); bounced=True
    if y<=0: y=0; dy=abs(dy); bounced=True
    elif y+h>=height: y=max(0,height-h); dy=-abs(dy); bounced=True
    return x,y,dx,dy,bounced

def next_colour(current, rng=random):
    """A colour other than the current one."""
    return rng.choice([c for c in COLOURS if c!=current] or list(COLOURS))

def logo_size(width, height, aspect=2.0):
    """The logo's size on a width x height screen: about a fifth of the width, never taller than a quarter of the height."""
    w=max(80,round(width/5)); h=round(w/aspect)
    if h>height/4: h=max(40,round(height/4)); w=round(h*aspect)
    return w,h

MISSING_CAIRO="The screen saver needs python3-gi-cairo. Install it with:  sudo apt install python3-gi-cairo"
def cairo_missing():
    """The screen saver draws with cairo through PyGObject (python3-gi-cairo): True when that is not installed."""
    try:
        import gi; gi.require_foreign("cairo"); return False
    except (ImportError,AttributeError): return True

def running(env=None):
    """The pid of a screen saver that is showing now, or None."""
    try:
        pid=int((runtime_dir(env)/PID_NAME).read_text().strip()); os.kill(pid,0); return pid
    except (OSError,ValueError): return None

def start(launcher, env=None):
    """Start `tvwcs screensaver` unless one is showing. Returns "" or why not."""
    import subprocess
    if running(env): return ""
    if cairo_missing(): return MISSING_CAIRO
    try: subprocess.Popen([str(launcher),"screensaver"],start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except OSError as exc: return f"Could not start the screen saver: {exc}"
    return ""

# ---------------------------------------------------------------------- the screen being off
def parse_monitor_off(text):
    """`xset q`: True when DPMS has the monitor off (or in standby or suspend)."""
    return any(f"Monitor is {state}" in text for state in ("Off","in Standby","in Suspend"))

def parse_sway_outputs_off(text):
    """`swaymsg -t get_outputs -r`: True when every active output's power is off."""
    import json
    try: outputs=[o for o in json.loads(text or "[]") if o.get("active")]
    except (ValueError,AttributeError): return False
    return bool(outputs) and not any(o.get("power",o.get("dpms",True)) for o in outputs)

def screen_off(env=None):
    """Whether the screen is switched off now: the screen saver never runs then."""
    import subprocess
    env=os.environ if env is None else env
    argv=["swaymsg","-t","get_outputs","-r"] if env.get("SWAYSOCK") else ["xset","q"]
    try: out=subprocess.run(argv,capture_output=True,text=True,timeout=3).stdout
    except (OSError,subprocess.SubprocessError): return False
    return parse_sway_outputs_off(out) if env.get("SWAYSOCK") else parse_monitor_off(out)

# ---------------------------------------------------------------------- drawing the logo (cairo)
BARCODE=(3,1,1,2,1,3,2,1,1,1,3,1,2,2,1,1,3,2,1,2,1,1,2,3,1)   # bar, gap, bar, gap... widths in units

def _rgb(colour): return tuple(int(colour[i:i+2],16)/255 for i in (1,3,5))

def _draw_disc_logo(cr, Pango, PangoCairo, w, h, colour, word, disc_word):
    """The DVD Video logo's shape: a wide italic word over a flat disc with a smaller word cut out of it. TVWCS's own
    (disc_word None) has a smaller oval of the same shape in the disc instead, filled with the bars of a barcode."""
    cr.set_source_rgb(*_rgb(colour))
    layout=PangoCairo.create_layout(cr)
    font=Pango.FontDescription.from_string(f"Sans Bold Italic {max(8,int(h*0.5))}px")
    layout.set_font_description(font); layout.set_text(word,-1)
    _ink,logical=layout.get_pixel_extents()
    scale_x=(w*0.96)/max(1,logical.width)
    cr.save(); cr.translate(w*0.02,0); cr.scale(scale_x,1); PangoCairo.show_layout(cr,layout); cr.restore()
    # the disc: a flat ellipse under the word
    top=h*0.64; dh=h*0.34; cx=w/2; cy=top+dh/2; rx,ry=w*0.46,dh/2
    cr.save(); cr.translate(cx,cy); cr.scale(rx,ry); cr.arc(0,0,1,0,6.2832); cr.restore(); cr.fill()
    cr.set_source_rgb(0,0,0)
    if disc_word is None:
        # an oval half the size, the same shape, and a vertical barcode cut out of the disc inside it
        irx,iry=rx*0.5,ry*0.5
        cr.save(); cr.translate(cx,cy); cr.scale(irx,iry); cr.arc(0,0,1,0,6.2832); cr.restore()
        cr.save(); cr.clip()
        unit=2*irx/sum(BARCODE); x=cx-irx
        for i,width in enumerate(BARCODE):
            if i%2==0: cr.rectangle(x,cy-iry,width*unit,2*iry)
            x+=width*unit
        cr.fill(); cr.restore()
        return
    small=PangoCairo.create_layout(cr)
    small.set_font_description(Pango.FontDescription.from_string(f"Sans Bold {max(6,int(dh*0.5))}px")); small.set_text(disc_word,-1)
    _ink,sl=small.get_pixel_extents()
    cr.move_to(cx-sl.width/2,cy-sl.height/2); PangoCairo.show_layout(cr,small)

LOGO_WORDS={"dvd":("DVD","VIDEO"),"tvwcs":("TVWCS",None)}
def logo_aspect(kind, picture=None):
    if picture is not None: return picture.get_width()/max(1,picture.get_height())
    return 2.0 if kind=="dvd" else 2.4

def paint_logo(cr, kind, w, h, colour, picture=None):
    """The logo, w x h at cr's origin: a picture (a cairo surface), else the DVD or TVWCS logo in `colour`."""
    if picture is not None:
        cr.save(); cr.scale(w/picture.get_width(),h/picture.get_height()); cr.set_source_surface(picture,0,0); cr.paint(); cr.restore()
        return
    import gi
    gi.require_version("PangoCairo","1.0")
    from gi.repository import Pango, PangoCairo
    _draw_disc_logo(cr,Pango,PangoCairo,w,h,colour,*LOGO_WORDS.get(kind,LOGO_WORDS["dvd"]))

def picture_surface(path):
    """A cairo surface with the picture at `path` (PNG, JPEG, SVG...), or None when it cannot be read."""
    try:
        import cairo, gi
        gi.require_version("GdkPixbuf","2.0"); gi.require_version("Gdk","4.0")
        from gi.repository import Gdk, GdkPixbuf
        pix=GdkPixbuf.Pixbuf.new_from_file(os.path.expanduser(path))
        surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,pix.get_width(),pix.get_height())
        cr=cairo.Context(surface); Gdk.cairo_set_source_pixbuf(cr,pix,0,0); cr.paint(); surface.flush()
        return surface
    except Exception: return None

# ---------------------------------------------------------------------- inside xsecurelock (X11, no GTK)
def run_in_window(settings, window_id, stop=None):
    """`tvwcs screensaver --xsecurelock`: xsecurelock runs this as its saver while the computer is locked (Settings >
    Power and sleep > Show the screen saver when locked). It draws into the window xsecurelock made for each monitor
    (XSCREENSAVER_WINDOW) through Xlib, since GTK cannot draw in another program's window. xsecurelock stops it when a
    key is pressed (and shows its password box), and when the screen turns off."""
    import ctypes, ctypes.util, math, time, cairo
    x11=ctypes.cdll.LoadLibrary(ctypes.util.find_library("X11") or "libX11.so.6")
    x11.XOpenDisplay.restype=ctypes.c_void_p; x11.XOpenDisplay.argtypes=[ctypes.c_char_p]
    x11.XDefaultScreen.argtypes=[ctypes.c_void_p]
    x11.XDefaultVisual.restype=ctypes.c_void_p; x11.XDefaultVisual.argtypes=[ctypes.c_void_p,ctypes.c_int]
    x11.XCreateGC.restype=ctypes.c_void_p; x11.XCreateGC.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_void_p]
    x11.XGetGeometry.argtypes=[ctypes.c_void_p,ctypes.c_ulong]+[ctypes.POINTER(ctypes.c_ulong)]+[ctypes.POINTER(ctypes.c_int)]*2+[ctypes.POINTER(ctypes.c_uint)]*4
    x11.XSetForeground.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong]
    x11.XFillRectangle.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_uint,ctypes.c_uint]
    x11.XCreateImage.restype=ctypes.c_void_p
    x11.XCreateImage.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_int,ctypes.c_int]
    x11.XPutImage.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_uint,ctypes.c_uint]
    x11.XFlush.argtypes=[ctypes.c_void_p]
    dpy=x11.XOpenDisplay(None)
    if not dpy: print("The screen saver cannot open the display.",file=sys.stderr); return 1
    root=ctypes.c_ulong(); gx=ctypes.c_int(); gy=ctypes.c_int(); W=ctypes.c_uint(); H=ctypes.c_uint(); border=ctypes.c_uint(); depth=ctypes.c_uint()
    if not x11.XGetGeometry(dpy,window_id,ctypes.byref(root),ctypes.byref(gx),ctypes.byref(gy),ctypes.byref(W),ctypes.byref(H),ctypes.byref(border),ctypes.byref(depth)):
        return 1
    width,height=W.value,H.value
    if depth.value not in (24,32): print(f"The screen saver needs a 24-bit display, not {depth.value}-bit.",file=sys.stderr); return 1
    gc=x11.XCreateGC(dpy,window_id,0,None); x11.XSetForeground(dpy,gc,0); x11.XFillRectangle(dpy,window_id,gc,0,0,width,height)
    kind=settings.get("screensaver_logo","dvd"); picture=None
    if kind=="image":
        picture=picture_surface(settings.get("screensaver_image",""))
        if picture is None: kind="dvd"
    w,h=logo_size(width,height,logo_aspect(kind,picture))
    speed=SPEED*max(1.0,height/1080); pad=math.ceil(speed)+2   # the black edge round the logo wipes where it was
    surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,w+2*pad,h+2*pad); stride=surface.get_stride()
    buffer=(ctypes.c_char*(stride*(h+2*pad))).from_buffer(surface.get_data())
    image=x11.XCreateImage(dpy,x11.XDefaultVisual(dpy,x11.XDefaultScreen(dpy)),depth.value,2,0,ctypes.addressof(buffer),w+2*pad,h+2*pad,32,stride)   # 2: ZPixmap
    x=random.uniform(0,max(1,width-w)); y=random.uniform(0,max(1,height-h)); dx=random.choice((speed,-speed)); dy=random.choice((speed,-speed))
    colour=COLOURS[0]; stop=stop or (lambda:False)
    while not stop():
        x,y,dx,dy,bounced=step(x,y,dx,dy,w,h,width,height)
        if bounced: colour=next_colour(colour)
        cr=cairo.Context(surface); cr.set_source_rgb(0,0,0); cr.paint(); cr.translate(pad,pad); paint_logo(cr,kind,w,h,colour,picture); surface.flush()
        x11.XPutImage(dpy,window_id,gc,image,0,0,round(x)-pad,round(y)-pad,w+2*pad,h+2*pad); x11.XFlush(dpy)
        time.sleep(FRAME_MS/1000)
    return 0

def saver_script(launcher, env=None):
    """The program xsecurelock runs as its saver (XSECURELOCK_SAVER takes a program, not a command line): a small
    script in the runtime directory that runs `tvwcs screensaver --xsecurelock`."""
    path=runtime_dir(env)/"tvwcs-lock-saver"
    text=f"#!/bin/sh\nexec '{launcher}' screensaver --xsecurelock\n"
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        if not path.is_file() or path.read_text()!=text: path.write_text(text)
        path.chmod(0o755)
    except OSError: return ""
    return str(path)

# ---------------------------------------------------------------------- the window (GTK)
def run(settings, preview=False):
    import gi
    gi.require_version("Gtk","4.0"); gi.require_version("Gdk","4.0"); gi.require_version("PangoCairo","1.0")
    from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo
    if cairo_missing(): print(MISSING_CAIRO,file=sys.stderr); return 1
    pid_file=runtime_dir()/PID_NAME
    if running() and not preview: return 0
    try: pid_file.parent.mkdir(parents=True,exist_ok=True); pid_file.write_text(str(os.getpid()))
    except OSError: pass
    kind=settings.get("screensaver_logo","dvd"); image=None
    if kind=="image":
        try: image=Gdk.Texture.new_from_filename(os.path.expanduser(settings.get("screensaver_image","")))
        except Exception: image=None   # an unreadable picture: the DVD logo instead
        if image is None: kind="dvd"
    state={"x":None,"y":40.0,"dx":SPEED,"dy":SPEED,"colour":COLOURS[0],"start":None,"pointer":None}

    app=Gtk.Application(application_id=None)
    def activate(_app):
        win=Gtk.ApplicationWindow(application=app,title="TVWCS · Screen saver"); win.set_decorated(False)
        css=Gtk.CssProvider(); css.load_from_data(b"window.saver { background: #000000; }"); win.add_css_class("saver")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        try: win.set_cursor_from_name("none")
        except (AttributeError,TypeError): pass
        area=Gtk.DrawingArea(); area.set_hexpand(True); area.set_vexpand(True); win.set_child(area)
        def draw(_a, cr, width, height):
            cr.set_source_rgb(0,0,0); cr.paint()
            pix=_texture_surface(image) if image is not None else None
            w,h=logo_size(width,height,logo_aspect(kind,pix))
            if state["x"] is None:   # a random place and direction to start, at a speed that suits the screen's size
                state["x"]=random.uniform(0,max(1,width-w)); state["y"]=random.uniform(0,max(1,height-h))
                speed=SPEED*max(1.0,height/1080); state["dx"]=random.choice((speed,-speed)); state["dy"]=random.choice((speed,-speed))
            x,y,dx,dy,bounced=step(state["x"],state["y"],state["dx"],state["dy"],w,h,width,height)
            state.update(x=x,y=y,dx=dx,dy=dy)
            if bounced: state["colour"]=next_colour(state["colour"])
            cr.save(); cr.translate(x,y); paint_logo(cr,kind if image is None else "dvd",w,h,state["colour"],pix); cr.restore()
        area.set_draw_func(draw)
        def tick(): area.queue_draw(); return GLib.SOURCE_CONTINUE
        GLib.timeout_add(FRAME_MS,tick)
        def watch_screen():   # never drawn on a screen that is off: it ends when the screen turns off
            if not preview and screen_off(): app.quit(); return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE
        GLib.timeout_add_seconds(2,watch_screen)
        quit_=lambda *_:(app.quit(),True)[1]
        keys=Gtk.EventControllerKey(); keys.connect("key-pressed",quit_); win.add_controller(keys)
        click=Gtk.GestureClick(); click.set_button(0); click.connect("pressed",quit_); win.add_controller(click)
        motion=Gtk.EventControllerMotion()
        def moved(_c,x,y):
            last=state["pointer"]; state["pointer"]=(x,y)
            if last is not None and abs(x-last[0])+abs(y-last[1])>8: app.quit()
        motion.connect("motion",moved); win.add_controller(motion)
        win.fullscreen(); win.present()
    app.connect("activate",activate)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGTERM,lambda:(app.quit(),GLib.SOURCE_REMOVE)[1])
    try: return app.run([])
    finally:
        try:
            if pid_file.read_text().strip()==str(os.getpid()): pid_file.unlink()
        except OSError: pass

_surfaces={}
def _texture_surface(texture):
    """A cairo surface with the texture's pixels (cached), for drawing a picture of the user's own."""
    if id(texture) in _surfaces: return _surfaces[id(texture)]
    try:
        import cairo
        w,h=texture.get_width(),texture.get_height(); stride=cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_ARGB32,w)
        data=bytearray(stride*h); texture.download(data,stride)   # GDK_MEMORY_DEFAULT is premultiplied BGRA, as cairo's ARGB32
        surface=cairo.ImageSurface.create_for_data(data,cairo.FORMAT_ARGB32,w,h,stride)
    except Exception: surface=None
    _surfaces[id(texture)]=surface; return surface
