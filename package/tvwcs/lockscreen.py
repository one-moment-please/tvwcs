"""TVWCS's lock screen: i3lock, or swaylock on sway, showing a picture in TVWCS's style that says the computer is
locked and how to unlock it. A TVWCS session (TV mode) always locks with it; a desktop session's own locker is left
alone. With the screen saver shown when locked (X11), xsecurelock locks instead and runs TVWCS's screen saver.

TVWCS does not draw the lock itself: a screen locker must grab the keyboard and keep the screen covered even if it
crashes, which i3lock and swaylock are built for. TVWCS only paints the picture they show (`tvwcs lock` renders it with
GTK, one per monitor, then starts the locker). Unlocking is as with any i3lock: type the password and press Enter.
The command half has no GTK dependency."""
from __future__ import annotations
import getpass, os, shutil, socket
from pathlib import Path

BACKGROUND="#1b1b1b"
TITLE="Locked"
def message(user):
    return f"A password is needed. Type {user}'s password, then press Enter to unlock."
HINT="Nothing shows while you type. A wrong password flashes in the circle in the middle of the screen."

def _sway(env): return bool(env.get("SWAYSOCK"))

def available(env=None, which=shutil.which):
    """The locker TVWCS's lock screen runs here: "swaylock" on sway, "i3lock" elsewhere, or "" when it is not installed."""
    env=os.environ if env is None else env
    name="swaylock" if _sway(env) else "i3lock"
    return name if which(name) else ""

def saver_lock(settings, env=None, which=shutil.which):
    """Locking shows the screen saver (Settings > Power and sleep > Show the screen saver when locked): xsecurelock
    locks, runs TVWCS's screen saver, and shows its password box when a key is pressed. X11 only: True when chosen
    and xsecurelock is installed."""
    env=os.environ if env is None else env
    return bool((settings or {}).get("screensaver_on_lock")) and not _sway(env) and bool(which("xsecurelock"))

AUTH_TIMEOUT=60   # seconds the password box waits for a key before the screen saver comes back
def xsecurelock_env(settings, saver, accent=None):
    """xsecurelock's settings (it reads them from the environment): TVWCS's saver, a minute's wait at the password
    box, and the screen left to TVWCS's own "Turn off the screen after" (and X's), never blanked by xsecurelock."""
    return {"XSECURELOCK_SAVER":saver,"XSECURELOCK_AUTH_TIMEOUT":str(AUTH_TIMEOUT),"XSECURELOCK_SAVER_STOP_ON_BLANK":"1",
            "XSECURELOCK_BLANK_TIMEOUT":"-1","XSECURELOCK_SHOW_USERNAME":"1","XSECURELOCK_SHOW_HOSTNAME":"1",
            "XSECURELOCK_PASSWORD_PROMPT":"asterisks","XSECURELOCK_AUTH_BACKGROUND_COLOR":BACKGROUND,
            "XSECURELOCK_AUTH_FOREGROUND_COLOR":"#ffffff","XSECURELOCK_FONT":"Open Sans:size=22",
            "XSECURELOCK_AUTH_WARNING_COLOR":accent or (settings or {}).get("accent","#0078d7")}

def launcher():
    """The tvwcs launcher script, next to the package (as main.LAUNCHER finds it)."""
    here=Path(__file__).resolve().parent
    for cand in (here.parent/"bin"/"tvwcs",here/"tvwcs",here.parent.parent/"bin"/"tvwcs"):
        if cand.exists(): return str(cand)
    return "tvwcs"

def command(settings, env=None, which=shutil.which):
    """`tvwcs lock` in TV mode (a TVWCS session) when its locker is installed, else None (the desktop's usual locker)."""
    from tvwcs.model import tv_mode
    env=os.environ if env is None else env
    if not tv_mode(env): return None
    if saver_lock(settings,env,which) or available(env,which): return [launcher(),"lock"]
    return None

def locker_argv(locker, images, color=BACKGROUND[1:], nofork=False):
    """The locker's command line. `images` is [(output name, png path)] for swaylock, or [("", one png for the whole
    X screen)] for i3lock. -e: an empty Enter is not a wrong password; -f (i3lock) / -F (swaylock): failed attempts show."""
    if locker=="swaylock":
        argv=["swaylock","-f","-e","-F","-c",color]
        for output,path in images: argv+=["-i",f"{output}:{path}" if output else path]
        return argv
    argv=["i3lock","-e","-f","-c",color]+(["-n"] if nofork else [])   # -n: xss-lock waits for it (as with Debian's `i3lock --nofork`)
    if images: argv+=["-i",images[0][1]]
    return argv

# ---------------------------------------------------------------------- painting the picture (GTK)
def _renderer(Gdk, Gsk, Gtk):
    r=Gsk.CairoRenderer.new()
    try: r.realize_for_display(Gdk.Display.get_default()); return r,None
    except (AttributeError,TypeError): pass
    try:
        if r.realize(None): return r,None
    except Exception: pass
    win=Gtk.Window(); win.realize(); return win.get_renderer(),win   # GTK before 4.14: an unmapped window's renderer

def _paint(snap, Gdk, Graphene, Pango, ctx, x, y, w, h, user, accent):
    def rgba(spec): c=Gdk.RGBA(); c.parse(spec); return c
    snap.append_color(rgba(BACKGROUND),Graphene.Rect().init(x,y,w,h))
    unit=max(0.6,h/1080)
    left=x+round(110*unit); width=min(w-2*round(110*unit),round(1100*unit))
    def text(markup, size, weight, color, top):
        layout=Pango.Layout.new(ctx); layout.set_width(width*Pango.SCALE); layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        fd=Pango.FontDescription.from_string(f"Segoe UI, Selawik, Open Sans, Noto Sans, sans {weight} {size*unit:.0f}px")
        fd.set_absolute_size(size*unit*Pango.SCALE); layout.set_font_description(fd); layout.set_text(markup,-1)
        snap.save(); snap.translate(Graphene.Point().init(left,top)); snap.append_layout(layout,rgba(color)); snap.restore()
        return layout.get_pixel_size()[1]
    bottom=y+h-round(120*unit)
    top=bottom-round(330*unit)
    snap.append_color(rgba(accent),Graphene.Rect().init(left,top,round(90*unit),round(8*unit)))   # the Metro accent bar
    top+=round(34*unit)
    top+=text(TITLE,96,"Light","#ffffff",top)+round(14*unit)
    top+=text(message(user),30,"Normal","#ffffff",top)+round(12*unit)
    text(HINT,20,"Normal","#9a9a9a",top)
    host=socket.gethostname().split(".")[0]
    text(host,20,"Normal","#7d7d7d",y+round(60*unit))

def render(out_dir, accent="#0078d7", user=None, sway=False):
    """Paint the lock picture(s) into out_dir: one per monitor on sway, one for the whole X screen otherwise.
    Returns [(output name, path)] ([] when there is no display)."""
    import gi
    gi.require_version("Gtk","4.0"); gi.require_version("Gdk","4.0"); gi.require_version("Gsk","4.0"); gi.require_version("Graphene","1.0")
    from gi.repository import Gdk, Graphene, Gsk, Gtk, Pango
    Gtk.init(); display=Gdk.Display.get_default()
    if display is None: return []
    user=user or getpass.getuser(); out_dir=Path(out_dir); out_dir.mkdir(parents=True,exist_ok=True)
    monitors=display.get_monitors(); rects=[]
    for i in range(monitors.get_n_items()):
        m=monitors.get_item(i); g=m.get_geometry(); f=max(1,m.get_scale_factor())
        rects.append((m.get_connector() or f"output{i}",g.x*f,g.y*f,g.width*f,g.height*f))
    if not rects: rects=[("",0,0,1920,1080)]
    ctx=Gtk.Label().create_pango_context()
    renderer,keep=_renderer(Gdk,Gsk,Gtk); images=[]
    try:
        groups=[[r] for r in rects] if sway else [rects]
        for group in groups:
            ox=min(r[1] for r in group); oy=min(r[2] for r in group)
            W=max(r[1]+r[3] for r in group)-ox; H=max(r[2]+r[4] for r in group)-oy
            snap=Gtk.Snapshot(); snap.append_color(Gdk.RGBA(red=0.106,green=0.106,blue=0.106,alpha=1),Graphene.Rect().init(0,0,W,H))
            for _name,x,y,w,h in group: _paint(snap,Gdk,Graphene,Pango,ctx,x-ox,y-oy,w,h,user,accent)
            tex=renderer.render_texture(snap.to_node(),Graphene.Rect().init(0,0,W,H))
            path=out_dir/(f"lock-{group[0][0]}.png" if sway else "lock.png"); tex.save_to_png(str(path))
            images.append((group[0][0] if sway else "",str(path)))
    finally:
        try: renderer.unrealize()
        except Exception: pass
        if keep is not None: keep.destroy()
    return images

def lock(settings=None, env=None, nofork=False):
    """`tvwcs lock [--nofork]`: paint the picture and start the locker. Falls back to a plain dark lock if painting fails.
    --nofork: i3lock stays in the foreground until unlocked (xss-lock runs it that way). With the screen saver shown
    while locked, xsecurelock locks instead (see saver_lock)."""
    from tvwcs.session import runtime_dir
    env=os.environ if env is None else env; settings=settings or {}
    if saver_lock(settings,env):   # the screen saver while locked; xsecurelock stays in the foreground until unlocked
        from tvwcs import screensaver
        saver=screensaver.saver_script(launcher(),env); screensaver.clear_screen_off(env)
        if saver:
            os.execvpe("xsecurelock",["xsecurelock"],{**env,**xsecurelock_env(settings,saver)})
    locker=available(env)
    if not locker:
        print("TVWCS's lock screen needs i3lock (or swaylock on sway).",file=__import__("sys").stderr); return 1
    try: images=render(runtime_dir()/"lockscreen",settings.get("accent","#0078d7"),sway=locker=="swaylock")
    except Exception as exc:   # never leave the computer unlocked because the picture could not be drawn
        print(f"Could not draw the lock screen ({exc}); locking with a plain screen.",file=__import__("sys").stderr); images=[]
    argv=locker_argv(locker,images,nofork=nofork)
    os.execvp(argv[0],argv)
