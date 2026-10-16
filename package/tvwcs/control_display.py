"""Displays for Settings: resolution, refresh rate, scale, arrangement and the primary display, through xrandr
(i3 and other X11 sessions) or swaymsg (sway). No GTK dependency.

Scale makes text and controls bigger. sway scales each display by itself, by any amount (`output X scale 1.5`). X11
has one scale for the whole session: apps read it from Xft.dpi (xrdb) and, for GTK, from XSETTINGS (xsettingsd), and
those only work in whole steps. A fractional scale on X11 is done as GNOME does it: apps draw at the next whole step
up and xrandr shrinks the picture to fit (150 % = drawn at 200 %, shown at 3/4 of that), which is a little softer and
costs the graphics card more; so Settings offers it only once "Fractional scaling" is on.

The arrangement is kept as "this display is right of / left of / above / below / the same as that one", so changing
one display's resolution moves its neighbours with it instead of leaving a gap or an overlap. What Settings
applies is saved to ~/.config/tvwcs/displays.json, and TVWCS applies it again when it starts with the same displays
connected (xrandr forgets everything at log-out; sway forgets runtime changes)."""
from __future__ import annotations
import copy, json, math, os, re, signal, subprocess
from dataclasses import dataclass, field
from pathlib import Path

from tvwcs.control_cmd import have, run
from tvwcs.model import CONFIG_HOME

SAVED=CONFIG_HOME/"tvwcs"/"displays.json"
XSETTINGS_CONF=CONFIG_HOME/"tvwcs"/"xsettingsd.conf"
XRESOURCES=Path.home()/".Xresources"
SCALES=(1.0,2.0,3.0)
FRACTIONAL_SCALES=(1.0,1.25,1.5,1.75,2.0,2.25,2.5,2.75,3.0)
MIN_SCALED_HEIGHT=540     # a scale is offered while the display still shows at least this many (logical) pixels high
RELATIONS=("right","left","below","above","mirror")
RELATION_TEXT={"right":"Right of {}","left":"Left of {}","below":"Below {}","above":"Above {}","mirror":"Same picture as {}"}

@dataclass
class Mode:
    width: int
    height: int
    interlaced: bool=False
    rates: list=field(default_factory=list)     # Hz, highest first
    names: dict=field(default_factory=dict)     # rate -> xrandr's name for the mode (usually "1920x1080")
    preferred: bool=False
    @property
    def key(self): return (self.width,self.height,self.interlaced)

@dataclass
class Output:
    name: str                    # the connector: HDMI-1 (xrandr), HDMI-A-1 (sway)
    label: str=""                # the display's own name when known (DELL U2720Q)
    enabled: bool=False
    primary: bool=False
    x: int=0
    y: int=0
    width: int=0                 # the mode in use, in pixels, before rotation and scaling
    height: int=0
    interlaced: bool=False
    rate: float=0.0
    rotated: bool=False          # turned a quarter (portrait): width and height swap on the desktop
    scale: float=1.0             # how much bigger things look: sway's output scale; on X11 ui / xrandr's --scale
    ui: float=1.0                # X11: the scale apps draw at (Xft.dpi / 96), the same on every display; 1 on sway
    modes: list=field(default_factory=list)
    @property
    def title(self): return self.label or self.name
    @property
    def size(self):
        """How much of the desktop it covers."""
        w,h=(self.height,self.width) if self.rotated else (self.width,self.height)
        z=(self.ui or 1)/(self.scale or 1)
        return (round(w*z),round(h*z))
    @property
    def zoom(self):
        """xrandr's --scale: how much of the desktop one of its pixels shows (1 unless the scale is fractional)."""
        return (self.ui or 1)/(self.scale or 1)
    def mode(self, key=None):
        key=key or (self.width,self.height,self.interlaced)
        return next((m for m in self.modes if m.key==key),None)
    def preferred_mode(self): return next((m for m in self.modes if m.preferred),self.modes[0] if self.modes else None)

@dataclass
class DisplayState:
    available: bool
    backend: str=""              # "xrandr" or "sway"
    message: str=""
    outputs: list=field(default_factory=list)   # connected displays only
    ui: float=1.0                # X11: Xft.dpi / 96
    fractional: bool=False       # X11: fractional scales are offered (Settings > Displays > Fractional scaling)
    max_size: tuple=(0,0)        # X11: the largest desktop the X server allows (a fractional scale needs a bigger one)
    @property
    def can_set_primary(self): return self.backend=="xrandr"   # sway has no primary display

# ---------------------------------------------------------------------- reading
def rate_text(rate):
    """60.0 -> '60 Hz', 59.94 -> '59.94 Hz'."""
    return f"{rate:.2f}".rstrip("0").rstrip(".")+" Hz"
def mode_text(mode):
    return f"{mode.width} × {mode.height}"+(" (interlaced)" if mode.interlaced else "")

def _add_rate(mode, rate, name):
    if not any(abs(r-rate)<0.005 for r in mode.rates): mode.rates.append(rate); mode.names[rate]=name
def _sort(modes):
    for m in modes: m.rates.sort(reverse=True)
    modes.sort(key=lambda m:(m.width*m.height,m.width,not m.interlaced),reverse=True)
    return modes

_OUTPUT=re.compile(r"^(\S+) (connected|disconnected|unknown connection)( primary)?(?: (\d+)x(\d+)\+(-?\d+)\+(-?\d+))?(?: (normal|left|inverted|right))?")
_MODE=re.compile(r"^\s+((\d+)x(\d+)(i?)\S*)\s+(.*)$")
def parse_xrandr(text):
    """`xrandr --query` -> the connected outputs. A connected output without a size after it is switched off."""
    outputs=[]; cur=None; desk={}
    for line in text.splitlines():
        m=_OUTPUT.match(line)
        if m:
            cur=None
            if m.group(2)!="connected": continue
            cur=Output(name=m.group(1),primary=bool(m.group(3)),enabled=m.group(4) is not None)
            if cur.enabled:
                cur.x,cur.y=int(m.group(6)),int(m.group(7)); cur.rotated=m.group(8) in ("left","right")
                w,h=int(m.group(4)),int(m.group(5)); cur.width,cur.height=(h,w) if cur.rotated else (w,h)
                desk[id(cur)]=cur.width   # what it covers of the desktop: more than its mode when xrandr --scale shrinks it
            outputs.append(cur); continue
        m=_MODE.match(line)
        if cur is None or not m: continue
        name,w,h,inter=m.group(1),int(m.group(2)),int(m.group(3)),m.group(4)=="i"
        mode=next((x for x in cur.modes if x.key==(w,h,inter)),None)
        if mode is None: mode=Mode(w,h,inter); cur.modes.append(mode)
        # rates look like "60.00*+  50.00    59.94": * is the one in use, + the display's preferred one
        rest=m.group(5)
        for rm in re.finditer(r"(\d+(?:\.\d+)?)(\*?)\s*(\+?)",rest):
            rate=float(rm.group(1)); _add_rate(mode,rate,name)
            if rm.group(2):
                cur.rate=rate; cur.width,cur.height=w,h; cur.interlaced=inter
            if rm.group(3): mode.preferred=True
    for o in outputs:
        _sort(o.modes)
        if desk.get(id(o)) and o.width: o.scale=round(o.width/desk[id(o)],6)   # with ui 1; read_state sets the ui
    return outputs

def parse_xft_dpi(text):
    """`xrdb -query` -> Xft.dpi, or 0 when it is not set."""
    m=re.search(r"^Xft\.dpi:\s*(\d+(?:\.\d+)?)",text or "",re.M)
    return float(m.group(1)) if m else 0.0

def read_ui():
    """X11: the scale apps draw at, from Xft.dpi (1 when it is not set)."""
    r=run(["xrdb","-query"],timeout=5) if have("xrdb") else None
    dpi=parse_xft_dpi(r.out) if r and r.ok else 0
    return round(dpi/96,3) if dpi>0 else 1.0

def with_ui(outputs, ui):
    """Outputs parsed from xrandr, at the session's ui: the scale each shows is ui over its zoom."""
    for o in outputs: o.scale=_round_scale((o.scale or 1)*ui); o.ui=ui
    return outputs

def _round_scale(s):
    q=round(s*4)/4
    return q if abs(q-s)<0.01 else round(s,2)

def parse_sway(text):
    """`swaymsg -t get_outputs -r` (JSON) -> the outputs. sway gives refresh rates in mHz."""
    try: data=json.loads(text or "[]")
    except ValueError: return []
    outputs=[]
    for d in data if isinstance(data,list) else []:
        if not isinstance(d,dict) or not d.get("name"): continue
        label=" ".join(x for x in (d.get("make"),d.get("model")) if x and x!="Unknown").strip()
        o=Output(name=d["name"],label=label,enabled=bool(d.get("active")),primary=False,
                 rotated=str(d.get("transform","normal")).replace("flipped-","") in ("90","270"),scale=float(d.get("scale") or 1) if d.get("active") else 1.0)
        rect=d.get("rect") or {}; o.x,o.y=int(rect.get("x",0)),int(rect.get("y",0))
        cm=d.get("current_mode") or {}
        if cm: o.width,o.height,o.rate=int(cm.get("width",0)),int(cm.get("height",0)),round(int(cm.get("refresh",0))/1000,3)
        for mode in d.get("modes") or []:
            w,h=int(mode.get("width",0)),int(mode.get("height",0)); rate=round(int(mode.get("refresh",0))/1000,3)
            m=next((x for x in o.modes if x.key==(w,h,False)),None)
            if m is None: m=Mode(w,h); o.modes.append(m)
            _add_rate(m,rate,f"{w}x{h}")
        pm=d.get("preferred_mode") or {}   # not in every sway version; else the largest mode counts as preferred
        _sort(o.modes)
        best=next((m for m in o.modes if (m.width,m.height)==(pm.get("width"),pm.get("height"))),o.modes[0] if o.modes else None)
        if best is not None: best.preferred=True
        outputs.append(o)
    return outputs

def backend(env=None, has=have):
    """Which tool drives the displays here: "sway", "xrandr", or "" (with why not)."""
    env=os.environ if env is None else env
    if env.get("SWAYSOCK"):
        return ("sway","") if has("swaymsg") else ("","swaymsg was not found (it comes with sway).")
    if env.get("WAYLAND_DISPLAY") and not env.get("DISPLAY"):
        return "","Display settings work in sway or in an X11 session such as i3; this Wayland session is neither."
    if not env.get("DISPLAY"): return "","There is no graphical session to change."
    return ("xrandr","") if has("xrandr") else ("","xrandr was not found. Install it (x11-xserver-utils) to change displays.")

def read_state():
    tool,why=backend()
    if not tool: return DisplayState(False,message=why)
    r=run(["swaymsg","-t","get_outputs","-r"] if tool=="sway" else ["xrandr","--query"],timeout=10)
    if not r.ok: return DisplayState(False,tool,f"Could not read the displays: {r.message}")
    outputs=parse_sway(r.out) if tool=="sway" else parse_xrandr(r.out)
    if not outputs: return DisplayState(False,tool,"No display was found.")
    if tool=="sway": return DisplayState(True,tool,"",outputs)
    ui=read_ui(); with_ui(outputs,ui)
    return DisplayState(True,tool,"",outputs,ui,fractional_on(outputs),parse_max_size(r.out))

# ---------------------------------------------------------------------- scale
def scale_text(s):
    """1.5 -> '150 %'."""
    return f"{round(s*100)} %"

def is_whole(s): return abs(s-round(s))<0.01

def fractional_on(outputs, path=None):
    """X11: whether fractional scales are offered: turned on in Settings, or one is in use."""
    try: saved=json.loads(Path(path or SAVED).read_text(encoding="utf-8"))
    except (OSError,ValueError): saved=None
    return bool(_entries(saved).get("xrandr",{}).get("fractional")) or any(o.enabled and not is_whole(o.scale) for o in outputs)

def set_fractional(on, path=None):
    path=Path(path or SAVED); path.parent.mkdir(parents=True,exist_ok=True)
    try: saved=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError): saved=None
    entries=_entries(saved); entries.setdefault("xrandr",{})["fractional"]=bool(on)
    tmp=path.with_suffix(".tmp"); tmp.write_text(json.dumps(entries,indent=2)+"\n",encoding="utf-8"); os.replace(tmp,path)

def scale_choices(outputs, fractional, current=None, max_size=None):
    """The scales to offer for these displays (one on sway; every one that is on, on X11): those that still leave each
    at least MIN_SCALED_HEIGHT pixels high, and the one in use. With max_size (X11), a fractional scale only when the
    bigger desktop it needs fits the X server."""
    heights=[(o.width if o.rotated else o.height) for o in outputs if o.enabled and o.width]
    out=[s for s in (FRACTIONAL_SCALES if fractional else SCALES) if s==1 or all(h/s>=MIN_SCALED_HEIGHT for h in heights)]
    if max_size: out=[s for s in out if is_whole(s) or fits(scaled(outputs,s),max_size)]
    if current and not any(abs(current-s)<0.005 for s in out): out=sorted(out+[current])
    return out

def session_scale(outputs):
    """X11: the scale shown for the whole session: the reference display's."""
    ref=reference(outputs)
    return ref.scale if ref else 1.0

def scaled(outputs, s):
    """X11: a copy of outputs all at scale s (apps draw at the whole step at or above it), arranged again."""
    new=copy.deepcopy(outputs); where=placements(new); ui=float(max(1,math.ceil(s-0.001)))
    for o in new: o.scale,o.ui=float(s),ui
    return arrange(new,where)

# ---------------------------------------------------------------------- arranging
def _rect(o): w,h=o.size; return (o.x,o.y,o.x+w,o.y+h)
def _overlap(a, b):
    ax,ay,ar,ab=a; bx,by,br,bb=b
    return ax<br and bx<ar and ay<bb and by<ab

def reference(outputs):
    """The display the others are arranged around: the primary one, else the first that is on."""
    on=[o for o in outputs if o.enabled]
    return next((o for o in on if o.primary),on[0] if on else None)

def relation(o, anchor):
    """Where o is, seen from anchor: one of RELATIONS."""
    ox,oy,orr,ob=_rect(o); ax,ay,ar,ab=_rect(anchor)
    if (ox,oy)==(ax,ay): return "mirror"
    if ox>=ar: return "right"
    if orr<=ax: return "left"
    if oy>=ab: return "below"
    if ob<=ay: return "above"
    dx=(ox+orr)-(ax+ar); dy=(oy+ob)-(ay+ab)   # overlapping: the way it leans
    if abs(dx)>=abs(dy): return "right" if dx>0 else "left"
    return "below" if dy>0 else "above"

def placements(outputs):
    """{name: (relation, anchor name)} for every display that is on, except the reference. Each display is anchored
    to the nearest one already placed, nearest to the reference first, so a row A B C reads "B right of A, C right of B"."""
    ref=reference(outputs)
    if ref is None: return {}
    rx,ry,rr,rb=_rect(ref); centre=lambda o:((_rect(o)[0]+_rect(o)[2])/2,(_rect(o)[1]+_rect(o)[3])/2)
    rc=((rx+rr)/2,(ry+rb)/2); dist=lambda a,b:abs(a[0]-b[0])+abs(a[1]-b[1])
    others=sorted((o for o in outputs if o.enabled and o is not ref),key=lambda o:dist(centre(o),rc))
    placed=[ref]; out={}
    for o in others:
        anchor=min(placed,key=lambda p:(_gap(o,p),-_shared(o,p),dist(centre(o),centre(p))))
        out[o.name]=(relation(o,anchor),anchor.name); placed.append(o)
    return out

def _gap(a, b):
    ax,ay,ar,ab=_rect(a); bx,by,br,bb=_rect(b)
    return max(bx-ar,ax-br,0)+max(by-ab,ay-bb,0)

def _shared(a, b):
    """How long an edge two displays share (0 when they only touch at a corner, or not at all)."""
    ax,ay,ar,ab=_rect(a); bx,by,br,bb=_rect(b)
    return max(0,min(ar,br)-max(ax,bx))+max(0,min(ab,bb)-max(ay,by))

def arrange(outputs, where):
    """Set every display's position from where = {name: (relation, anchor name)}: each is put against its anchor (top
    or left edges lined up), past any display already in that spot, and the whole desktop then starts at 0,0."""
    by_name={o.name:o for o in outputs}; ref=reference(outputs)
    if ref is None: return outputs
    ref.x=ref.y=0; done={ref.name}; todo=[o for o in outputs if o.enabled and o is not ref]
    def anchor_of(o):   # an anchor that is off, missing or the display itself: the reference instead
        rel,a=where.get(o.name,("right",ref.name))
        return rel,(a if a in by_name and by_name[a].enabled and a!=o.name else ref.name)
    while todo:
        ready=[o for o in todo if anchor_of(o)[1] in done]
        o=ready[0] if ready else todo[0]   # a loop: arranged around the reference
        rel,a=anchor_of(o)
        _place(o,rel,by_name[a] if a in done else ref,[by_name[n] for n in done]); done.add(o.name); todo.remove(o)
    on=[o for o in outputs if o.enabled]
    mx=min(o.x for o in on); my=min(o.y for o in on)
    for o in on: o.x-=mx; o.y-=my
    return outputs

def _place(o, rel, anchor, placed):
    w,h=o.size; aw,ah=anchor.size
    if rel=="mirror": o.x,o.y=anchor.x,anchor.y; return
    o.x,o.y={"right":(anchor.x+aw,anchor.y),"left":(anchor.x-w,anchor.y),"below":(anchor.x,anchor.y+ah),"above":(anchor.x,anchor.y-h)}.get(rel,(anchor.x+aw,anchor.y))
    for _ in range(len(placed)+1):
        hit=next((p for p in placed if p is not o and _overlap(_rect(o),_rect(p))),None)
        if hit is None: return
        hx,hy,hr,hb=_rect(hit)
        if rel=="right": o.x=hr
        elif rel=="left": o.x=hx-w
        elif rel=="below": o.y=hb
        else: o.y=hy-h

def choices(outputs, o):
    """[(key, text)] for where o can go: "relation:anchor" against every other display that is on."""
    out=[]
    for a in outputs:
        if a is o or not a.enabled: continue
        out+=[(f"{rel}:{a.name}",RELATION_TEXT[rel].format(a.title)) for rel in RELATIONS]
    return out

def best_rate(mode, wanted):
    """The rate to use for mode: wanted when it has it, else its highest."""
    near=[r for r in mode.rates if abs(r-wanted)<0.02]
    return near[0] if near else (mode.rates[0] if mode.rates else 0.0)

# ---------------------------------------------------------------------- changing
def edited(outputs, name, **changes):
    """A copy of outputs with changes to one display (enabled, mode=(w,h,interlaced), rate, primary, place=(rel, anchor)),
    arranged again so the others stay against it."""
    new=copy.deepcopy(outputs); where=placements(new); o=next(x for x in new if x.name==name)
    if "mode" in changes:
        m=o.mode(changes["mode"])
        if m is not None: o.width,o.height,o.interlaced=m.width,m.height,m.interlaced; o.rate=best_rate(m,changes.get("rate",o.rate))
    elif "rate" in changes: o.rate=changes["rate"]
    if "scale" in changes: o.scale=float(changes["scale"])
    if "enabled" in changes:
        o.enabled=changes["enabled"]
        if o.enabled:
            ref=reference(new)
            if ref is not None and ref is not o and ref.ui!=1: o.ui,o.scale=ref.ui,ref.scale   # X11: one scale for all
            if not o.width:
                m=o.preferred_mode()
                if m is not None: o.width,o.height,o.interlaced,o.rate=m.width,m.height,m.interlaced,m.rates[0] if m.rates else 0
            on=[x for x in new if x.enabled and x is not o]
            if on and o.name not in where: where[o.name]=("right",max(on,key=lambda x:x.x+x.size[0]).name)
        else:
            if o.primary:
                o.primary=False
                nxt=next((x for x in new if x.enabled),None)
                if nxt is not None: nxt.primary=True
            for k,(rel,anchor) in list(where.items()):   # whatever leaned on it now leans on what it leaned on
                if anchor==name: where[k]=where.get(name,(rel,(reference(new) or o).name))
            where.pop(name,None)
    if changes.get("primary"):
        for x in new: x.primary=x is o
        return new   # only the flag changes: the picture stays where it is
    if "place" in changes:
        rel,anchor=changes["place"]; where[name]=(rel,anchor)
        if anchor in where and where[anchor][1]==name: where.pop(anchor)   # it was anchored to this one: no loop
        ref=reference(new)
        if ref is not None and ref.name==name:   # moving the reference: keep it fixed, move the rest around it instead
            where.pop(name); where[anchor]=({"right":"left","left":"right","below":"above","above":"below"}.get(rel,rel),name)
    return arrange(new,where)

def xrandr_argv(outputs, zoomed=()):
    """zoomed: the outputs xrandr shows scaled now. --scale is given only to those and to the ones to scale, since
    some X servers and drivers (Xvfb, some virtual machines) refuse any transform, even 1x1."""
    argv=["xrandr"]
    for o in outputs:
        if not o.enabled: argv+=["--output",o.name,"--off"]; continue
        m=o.mode(); name=(m.names.get(o.rate) or next(iter(m.names.values()),None)) if m else None
        argv+=["--output",o.name,"--mode",name or f"{o.width}x{o.height}"]
        if o.rate: argv+=["--rate",f"{o.rate:.2f}"]
        if abs(o.zoom-1)>1e-6 or o.name in zoomed: z=f"{o.zoom:.10g}"; argv+=["--scale",f"{z}x{z}"]
        argv+=["--pos",f"{o.x}x{o.y}"]
        if o.primary: argv+=["--primary"]
    if not any(o.primary and o.enabled for o in outputs): argv+=["--noprimary"]
    return argv

def sway_command(outputs):
    parts=[]
    for o in outputs:
        q='"'+o.name.replace('"','')+'"'
        if not o.enabled: parts.append(f"output {q} disable"); continue
        parts.append(f"output {q} enable mode {o.width}x{o.height}@{o.rate:.3f}Hz scale {o.scale:g} position {o.x} {o.y}")
    return "; ".join(parts)

def apply(state, outputs):
    """Use these settings now. "" when it worked, else why not."""
    if not any(o.enabled for o in outputs): return "At least one display has to stay on."
    if state.backend=="sway": r=run(["swaymsg",sway_command(outputs)],timeout=20)
    else:
        now=run(["xrandr","--query"],timeout=10)   # what is scaled now (going back may have to undo a scale)
        zoomed={o.name for o in parse_xrandr(now.out) if o.enabled and abs(o.scale-1)>1e-3} if now.ok else set()
        r=run(xrandr_argv(outputs,zoomed),timeout=20)
    if r.ok and state.backend=="sway" and '"success": false' in r.out.replace("\n",""): return "sway did not accept the change."
    if not r.ok: return xrandr_problem(r) if state.backend=="xrandr" else (r.message or "The displays did not accept the change.")
    if state.backend=="xrandr":
        ui=next((o.ui for o in outputs if o.enabled),1.0)
        if abs(ui-read_ui())>0.001 or ui!=1: return set_ui(ui)
    return ""

def xrandr_problem(r):
    """xrandr's failure in words: an X error's first line (its last is only a serial number)."""
    text=r.err or r.out or ""
    if "cannot be larger than" in text:
        return "The graphics cannot make the picture that big (" + text.strip().splitlines()[-1].replace("xrandr: ","") + "). Try a whole step instead."
    m=re.search(r"^X Error of failed request:\s*(.*)$",text,re.M)
    if m: return f"The displays did not accept the change: {m.group(1).strip()}"
    return r.message or "The displays did not accept the change."

def parse_max_size(text):
    """`xrandr --query`'s first line -> the largest desktop the X server allows, (0, 0) when unknown."""
    m=re.search(r"maximum (\d+) x (\d+)",text or "")
    return (int(m.group(1)),int(m.group(2))) if m else (0,0)

def fits(outputs, max_size):
    """Whether the desktop these outputs cover fits the X server's largest one."""
    if not max_size or not max_size[0]: return True
    on=[o for o in outputs if o.enabled]
    if not on: return True
    w=max(o.x+o.size[0] for o in on)-min(o.x for o in on); h=max(o.y+o.size[1] for o in on)-min(o.y for o in on)
    return w<=max_size[0] and h<=max_size[1]

# ---------------------------------------------------------------------- X11: the scale apps draw at
def xresources_text(ui):
    return f"Xft.dpi: {round(96*ui)}\nXcursor.size: {round(24*ui)}\n"

def xsettings_text(ui):
    """GTK reads its scale from XSETTINGS: a whole window scale, and the font DPI (as GNOME's settings daemon sets them)."""
    whole=max(1,int(ui+0.001)); dpi=round(96*ui*1024)
    return f"Gdk/WindowScalingFactor {whole}\nGdk/UnscaledDPI {round(dpi/whole)}\nXft/DPI {dpi}\n"

def set_ui(ui, conf=None):
    """Make apps draw at ui: Xft.dpi for most toolkits, XSETTINGS (xsettingsd) for GTK. Apps already open take
    Xft.dpi only when they start again; GTK apps follow XSETTINGS at once. "" when it worked, else why not."""
    if not have("xrdb"): return "xrdb was not found. Install it (x11-xserver-utils) to change the scale."
    r=run(["xrdb","-merge"],timeout=10,input=xresources_text(ui))
    if not r.ok: return f"Could not set the scale: {r.message}"
    xsettings(ui,conf)
    return ""

def xsettings(ui, conf=None):
    """Hand GTK the scale through xsettingsd: TVWCS's own one is told to read its file again; none running, one is
    started (it ends with the X session). One started with another file is left alone."""
    if not have("xsettingsd"): return False
    conf=Path(conf or XSETTINGS_CONF); conf.parent.mkdir(parents=True,exist_ok=True); conf.write_text(xsettings_text(ui),encoding="utf-8")
    r=run(["pgrep","-u",str(os.getuid()),"-a","xsettingsd"],timeout=5)
    running=[l.split(None,1) for l in r.out.splitlines() if l.strip()] if r.ok else []
    ours=[int(p) for p,*cmd in running if str(conf) in " ".join(cmd)]
    if ours:
        for pid in ours:
            try: os.kill(pid,signal.SIGHUP)
            except OSError: pass
        return True
    if running or ui==1: return False
    try:
        subprocess.Popen(["xsettingsd","-c",str(conf)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        return True
    except OSError: return False

_MARK=("! Scale, set by TVWCS (Settings > Displays)","! End of TVWCS's scale")
def with_xresources(text, ui):
    """~/.Xresources with TVWCS's scale lines (read again at every X log-in, so i3 itself draws at it too); none at 1."""
    lines=(text or "").splitlines(); out=[]; skip=False
    for l in lines:
        if l.strip()==_MARK[0]: skip=True; continue
        if skip:
            if l.strip()==_MARK[1]: skip=False
            continue
        out.append(l)
    while out and not out[-1].strip(): out.pop()
    if ui!=1: out+=([""] if out else [])+[_MARK[0]]+xresources_text(ui).splitlines()+[_MARK[1]]
    return "\n".join(out)+("\n" if out else "")

def save_xresources(ui, path=None):
    path=Path(path or XRESOURCES)
    try: old=path.read_text(encoding="utf-8")
    except FileNotFoundError: old=""
    new=with_xresources(old,ui)
    if new==old: return
    if not new.strip() and _MARK[0] in old:   # only TVWCS's lines were in it
        path.unlink(missing_ok=True); return
    tmp=path.with_name(path.name+".tvwcs-tmp"); tmp.write_text(new,encoding="utf-8"); os.replace(tmp,path)

# ---------------------------------------------------------------------- keeping it
# displays.json keeps one entry per backend ({"xrandr": {"outputs": …}, "sway": {…}}), since i3 (X) and sway name the
# same connector differently (HDMI-1 / HDMI-A-1): keeping a mode under one never overwrites the other's. A file from
# before 3.0.1 ({"backend": …, "outputs": …}) is read as the entry for its backend.
def _entries(saved):
    if not isinstance(saved,dict): return {}
    if "backend" in saved and "outputs" in saved: return {str(saved["backend"]):{"outputs":saved["outputs"]}}
    return {k:v for k,v in saved.items() if k in ("xrandr","sway") and isinstance(v,dict)}

def to_saved(state, outputs, saved=None):
    entries=_entries(saved)
    entry={k:v for k,v in entries.get(state.backend,{}).items() if k!="outputs"}   # the fractional choice stays
    entry["outputs"]={o.name:{"enabled":o.enabled,"primary":o.primary,"x":o.x,"y":o.y,"width":o.width,
            "height":o.height,"interlaced":o.interlaced,"rate":o.rate,"scale":o.scale,"ui":o.ui} for o in outputs}
    entries[state.backend]=entry
    return entries

def save(state, outputs, path=SAVED):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(".tmp")
    try: saved=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError): saved=None
    tmp.write_text(json.dumps(to_saved(state,outputs,saved),indent=2)+"\n",encoding="utf-8"); os.replace(tmp,path)
    if state.backend=="xrandr" and path==SAVED: save_xresources(next((o.ui for o in outputs if o.enabled),1.0))

def connector_key(name):
    """A connector name the same under X and sway: X's HDMI-1 is sway's HDMI-A-1 (DRM's HDMI type A)."""
    return re.sub(r"^HDMI-A-","HDMI-",str(name))

def _matching(state, want):
    """`want` (name -> settings) keyed by the names connected now, or None when they are other displays."""
    names={o.name for o in state.outputs}
    if set(want)==names: return want
    by_key={connector_key(k):v for k,v in want.items()}
    if len(by_key)==len(want) and set(by_key)=={connector_key(n) for n in names}: return {n:by_key[connector_key(n)] for n in names}
    if len(want)==1 and len(names)==1: return {next(iter(names)):next(iter(want.values()))}   # one display either way
    return None

def from_saved(state, saved):
    """The saved settings applied to what is connected now, or None when they were saved for other displays. Without
    an entry for this backend, the other backend's is used (the first time sway runs, it gets the mode kept under i3)."""
    entries=_entries(saved)
    order=[state.backend]+[b for b in entries if b!=state.backend]
    want=None; same=False
    for b in order:
        if b in entries and entries[b].get("outputs"):
            want=_matching(state,entries[b].get("outputs") or {}); same=b==state.backend
            break
    if not want: return None
    new=copy.deepcopy(state.outputs)
    for o in new:
        s=want[o.name]; o.enabled=bool(s.get("enabled")); o.primary=bool(s.get("primary")); o.x,o.y=int(s.get("x",0)),int(s.get("y",0))
        m=o.mode((int(s.get("width",0)),int(s.get("height",0)),bool(s.get("interlaced"))))
        if o.enabled and m is None: return None   # that mode is gone (another display on the same connector)
        if m is not None: o.width,o.height,o.interlaced,o.rate=m.width,m.height,m.interlaced,best_rate(m,float(s.get("rate",0)))
        if same and "scale" in s:   # another backend's scale is left out: sway scales each display, X11 the session
            try: o.scale,o.ui=float(s["scale"]) or 1.0,float(s.get("ui",1)) or 1.0
            except (TypeError,ValueError): pass
    return new if any(o.enabled for o in new) else None

def restore(path=SAVED):
    """Apply the saved settings if they were saved for the displays connected now (TVWCS calls this as it starts)."""
    try: saved=json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError,ValueError): return ""
    state=read_state()
    if not state.available: return state.message
    new=from_saved(state,saved)
    if new is None: return ""
    look=lambda outs:[(o.enabled,o.primary,o.x,o.y,o.width,o.height,o.rate,o.scale,o.ui) for o in outs]
    if look(new)==look(state.outputs):
        if state.backend=="xrandr" and state.ui!=1: xsettings(state.ui)   # Xft.dpi came from ~/.Xresources: GTK needs XSETTINGS too
        return ""
    return apply(state,new)
