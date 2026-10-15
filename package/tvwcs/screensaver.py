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

# ---------------------------------------------------------------------- the window (GTK)
def _draw_disc_logo(cr, Pango, PangoCairo, w, h, colour, word, disc_word):
    """The DVD Video logo's shape: a wide italic word over a flat disc with a smaller word cut out of it."""
    r,g,b=(int(colour[i:i+2],16)/255 for i in (1,3,5))
    cr.set_source_rgb(r,g,b)
    layout=PangoCairo.create_layout(cr)
    font=Pango.FontDescription.from_string(f"Sans Bold Italic {max(8,int(h*0.5))}px")
    layout.set_font_description(font); layout.set_text(word,-1)
    _ink,logical=layout.get_pixel_extents()
    scale_x=(w*0.96)/max(1,logical.width)
    cr.save(); cr.translate(w*0.02,0); cr.scale(scale_x,1); PangoCairo.show_layout(cr,layout); cr.restore()
    # the disc: a flat ellipse under the word, with the second word cut out of it in black
    top=h*0.64; dh=h*0.34; cx=w/2; cy=top+dh/2
    cr.save(); cr.translate(cx,cy); cr.scale(w*0.46,dh/2); cr.arc(0,0,1,0,6.2832); cr.restore(); cr.fill()
    small=PangoCairo.create_layout(cr)
    small.set_font_description(Pango.FontDescription.from_string(f"Sans Bold {max(6,int(dh*0.5))}px")); small.set_text(disc_word,-1)
    _ink,sl=small.get_pixel_extents()
    cr.set_source_rgb(0,0,0); cr.move_to(cx-sl.width/2,cy-sl.height/2); PangoCairo.show_layout(cr,small)

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
    words={"dvd":("DVD","VIDEO"),"tvwcs":("TVWCS","TV")}.get(kind,("DVD","VIDEO"))
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
            if image is not None: w,h=logo_size(width,height,image.get_width()/max(1,image.get_height()))
            else: w,h=logo_size(width,height,2.0 if kind=="dvd" else 2.4)
            if state["x"] is None:   # a random place and direction to start, at a speed that suits the screen's size
                state["x"]=random.uniform(0,max(1,width-w)); state["y"]=random.uniform(0,max(1,height-h))
                speed=SPEED*max(1.0,height/1080); state["dx"]=random.choice((speed,-speed)); state["dy"]=random.choice((speed,-speed))
            x,y,dx,dy,bounced=step(state["x"],state["y"],state["dx"],state["dy"],w,h,width,height)
            state.update(x=x,y=y,dx=dx,dy=dy)
            if bounced: state["colour"]=next_colour(state["colour"])
            cr.save(); cr.translate(x,y)
            if image is not None:
                pix=_texture_surface(image)
                if pix is not None:
                    cr.scale(w/image.get_width(),h/image.get_height()); cr.set_source_surface(pix,0,0); cr.paint()
            else: _draw_disc_logo(cr,Pango,PangoCairo,w,h,state["colour"],*words)
            cr.restore()
        area.set_draw_func(draw)
        def tick(): area.queue_draw(); return GLib.SOURCE_CONTINUE
        GLib.timeout_add(FRAME_MS,tick)
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
