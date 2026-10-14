"""Displays for the Control Panel: resolution, refresh rate, arrangement and the primary display, through xrandr
(i3 and other X11 sessions) or swaymsg (sway). No GTK dependency.

The arrangement is kept as "this display is right of / left of / above / below / the same as that one", so changing
one display's resolution moves its neighbours with it instead of leaving a gap or an overlap. What the Control Panel
applies is saved to ~/.config/tvwcs/displays.json, and TVWCS applies it again when it starts with the same displays
connected (xrandr forgets everything at log-out; sway forgets runtime changes)."""
from __future__ import annotations
import copy, json, os, re
from dataclasses import dataclass, field
from pathlib import Path

from tvwcs.control_cmd import have, run
from tvwcs.model import CONFIG_HOME

SAVED=CONFIG_HOME/"tvwcs"/"displays.json"
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
    scale: float=1.0             # sway's output scale
    modes: list=field(default_factory=list)
    @property
    def title(self): return self.label or self.name
    @property
    def size(self):
        """How much of the desktop it covers."""
        w,h=(self.height,self.width) if self.rotated else (self.width,self.height)
        return (round(w/(self.scale or 1)),round(h/(self.scale or 1)))
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
    outputs=[]; cur=None
    for line in text.splitlines():
        m=_OUTPUT.match(line)
        if m:
            cur=None
            if m.group(2)!="connected": continue
            cur=Output(name=m.group(1),primary=bool(m.group(3)),enabled=m.group(4) is not None)
            if cur.enabled:
                cur.x,cur.y=int(m.group(6)),int(m.group(7)); cur.rotated=m.group(8) in ("left","right")
                w,h=int(m.group(4)),int(m.group(5)); cur.width,cur.height=(h,w) if cur.rotated else (w,h)
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
                cur.rate=rate
                if not cur.enabled or not cur.width: cur.width,cur.height=w,h
                cur.interlaced=inter
            if rm.group(3): mode.preferred=True
    for o in outputs: _sort(o.modes)
    return outputs

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
    return ("xrandr","") if has("xrandr") else ("","xrandr was not found. Install it (x11-xserver-utils, or xorg-xrandr) to change displays.")

def read_state():
    tool,why=backend()
    if not tool: return DisplayState(False,message=why)
    r=run(["swaymsg","-t","get_outputs","-r"] if tool=="sway" else ["xrandr","--query"],timeout=10)
    if not r.ok: return DisplayState(False,tool,f"Could not read the displays: {r.message}")
    outputs=parse_sway(r.out) if tool=="sway" else parse_xrandr(r.out)
    if not outputs: return DisplayState(False,tool,"No display was found.")
    return DisplayState(True,tool,"",outputs)

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
    if "enabled" in changes:
        o.enabled=changes["enabled"]
        if o.enabled:
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

def xrandr_argv(outputs):
    argv=["xrandr"]
    for o in outputs:
        if not o.enabled: argv+=["--output",o.name,"--off"]; continue
        m=o.mode(); name=(m.names.get(o.rate) or next(iter(m.names.values()),None)) if m else None
        argv+=["--output",o.name,"--mode",name or f"{o.width}x{o.height}"]
        if o.rate: argv+=["--rate",f"{o.rate:.2f}"]
        argv+=["--pos",f"{o.x}x{o.y}"]
        if o.primary: argv+=["--primary"]
    if not any(o.primary and o.enabled for o in outputs): argv+=["--noprimary"]
    return argv

def sway_command(outputs):
    parts=[]
    for o in outputs:
        q='"'+o.name.replace('"','')+'"'
        if not o.enabled: parts.append(f"output {q} disable"); continue
        parts.append(f"output {q} enable mode {o.width}x{o.height}@{o.rate:.3f}Hz position {o.x} {o.y}")
    return "; ".join(parts)

def apply(state, outputs):
    """Use these settings now. "" when it worked, else why not."""
    if not any(o.enabled for o in outputs): return "At least one display has to stay on."
    if state.backend=="sway": r=run(["swaymsg",sway_command(outputs)],timeout=20)
    else: r=run(xrandr_argv(outputs),timeout=20)
    if r.ok and state.backend=="sway" and '"success": false' in r.out.replace("\n",""): return "sway did not accept the change."
    return "" if r.ok else (r.message or "The displays did not accept the change.")

# ---------------------------------------------------------------------- keeping it
def to_saved(state, outputs):
    return {"backend":state.backend,"outputs":{o.name:{"enabled":o.enabled,"primary":o.primary,"x":o.x,"y":o.y,"width":o.width,
            "height":o.height,"interlaced":o.interlaced,"rate":o.rate} for o in outputs}}

def save(state, outputs, path=SAVED):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(to_saved(state,outputs),indent=2)+"\n",encoding="utf-8"); os.replace(tmp,path)

def from_saved(state, saved):
    """The saved settings applied to what is connected now, or None when they were saved for other displays."""
    if not isinstance(saved,dict) or saved.get("backend")!=state.backend: return None
    want=saved.get("outputs") or {}
    if set(want)!={o.name for o in state.outputs}: return None
    new=copy.deepcopy(state.outputs)
    for o in new:
        s=want[o.name]; o.enabled=bool(s.get("enabled")); o.primary=bool(s.get("primary")); o.x,o.y=int(s.get("x",0)),int(s.get("y",0))
        m=o.mode((int(s.get("width",0)),int(s.get("height",0)),bool(s.get("interlaced"))))
        if o.enabled and m is None: return None   # that mode is gone (another display on the same connector)
        if m is not None: o.width,o.height,o.interlaced,o.rate=m.width,m.height,m.interlaced,best_rate(m,float(s.get("rate",0)))
    return new if any(o.enabled for o in new) else None

def restore(path=SAVED):
    """Apply the saved settings if they were saved for the displays connected now (TVWCS calls this as it starts)."""
    try: saved=json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError,ValueError): return ""
    state=read_state()
    if not state.available: return state.message
    new=from_saved(state,saved)
    if new is None: return ""
    if [(o.enabled,o.primary,o.x,o.y,o.width,o.height,o.rate) for o in new]==[(o.enabled,o.primary,o.x,o.y,o.width,o.height,o.rate) for o in state.outputs]: return ""
    return apply(state,new)
