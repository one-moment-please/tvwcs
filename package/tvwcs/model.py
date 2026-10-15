"""TVWCS preferences, profiles, layout maths and search helpers; no GTK dependency."""
from __future__ import annotations
import copy, json, os, re, shlex, uuid
from dataclasses import dataclass, asdict
from pathlib import Path

from tvwcs.hotkeys import ACTION_LABELS, DEFAULT_HOTKEYS, DEVICE_LABELS, assigned, clean_hotkeys, valid_spec
from tvwcs.pinlock import valid_hash
from tvwcs.power import clean_idle

CONFIG_HOME=Path(os.environ.get("XDG_CONFIG_HOME",str(Path.home()/".config")))
DEFAULT_CONFIG=CONFIG_HOME/"tvwcs"/"config.json"

# How a profile is placed when launched or when its open window is selected.
LAUNCH_SAME="same"                  # tile alongside whatever is on the current workspace
LAUNCH_NEW_WORKSPACE="new_workspace"  # always get a workspace of its own
LAUNCH_MODES=(LAUNCH_SAME,LAUNCH_NEW_WORKSPACE)

# TVWCS's own windows are recognised by title. The prefix is deliberately unusual: a document called
# "tvwcs notes" in a text editor must never be mistaken for one of them (it would vanish from Open applications).
MAIN_TITLE="TVWCS"
DIALOG_PREFIX="TVWCS · "
def is_tvwcs_title(title: str) -> bool:
    return title==MAIN_TITLE or (title or "").startswith(DIALOG_PREFIX)

SCALE_PRESETS={"desktop":1.0,"tenfoot":1.6,"tenfoot_4k":3.0}
SCALE_LABELS={"desktop":"Desktop","tenfoot":"TV Mode","tenfoot_4k":"4K TV Mode"}
UHD_SCALES=("tenfoot_4k",)   # only offered when a 4K (3840×2160) or larger display is connected

def scale_choices(current, has_4k_display):
    """The interface sizes to offer: 4K TV Mode needs a 4K display, unless it is the one already chosen."""
    return [(k,v) for k,v in SCALE_LABELS.items() if has_4k_display or k not in UHD_SCALES or k==current]

def is_4k(width, height) -> bool:
    return max(width,height)>=3840 and min(width,height)>=2160
STARTUP_MODES=("none","menu","last","app")
STARTUP_LABELS={"none":"None","menu":"TVWCS Quick Menu","last":"Last application","app":"Chosen application"}

# How TVWCS is used, asked by install.sh and changeable in Settings > Options: it sets the interface size and where
# apps open (TV: each in a workspace of its own, full screen; desktop: tiled beside what is open). "" = never chosen.
USES={"tv":"TV","desktop":"Desktop"}
def apply_use(settings, use):
    if use not in USES: raise ValueError(f"Unknown use: {use}")
    settings["use"]=use; tv=use=="tv"
    if tv and settings["scale"]=="desktop": settings["scale"]="tenfoot"
    if not tv: settings["scale"]="desktop"
    settings["always_new_workspace"]=tv; settings["open_in_new_workspace"]=tv

DEFAULT_SETTINGS={
    "margin":20,                    # px (at desktop scale) between the panels and the edges of the usable workspace
    "quick_width":460,              # px (at desktop scale) width of the Quick Menu; the Settings panel matches it
    "accent":"#0078d7",             # Metro accent colour
    "lock_command":"",              # empty = auto-detect a screen locker
    "use":"",                       # "tv" or "desktop" (see USES), "" until chosen
    "scale":"desktop",              # key of SCALE_PRESETS
    "close_on_click_outside":False, # hide TVWCS when another window takes focus
    "open_in_new_workspace":False,  # selecting an open app gives it its own workspace instead of tiling it here
    "always_new_workspace":False,   # every app, launched or already open, opens in a workspace of its own
    "hide_options_buttons":False,   # fold the ☰ options buttons away; right-click (or ←) still opens each row's options
    "button_hints":False,           # show an icon-only button's tooltip after it has been selected for a few seconds
    "quick_settings_button":True,   # the Quick Menu's ⚙ button, which opens the Settings app
    "quick_close_button":True,      # the Quick Menu's ✕ button (Esc and Back close it too)
    "quick_lock_button":False,      # a Lock button in the Quick Menu's power menu
    "update_prereleases":False,     # TVWCS's updater also offers prereleases (releases not yet tested and marked latest)
    "clock_24h":False,              # the Quick Menu's clock shows 14:05 instead of 2:05 PM
    "tv_hide_bar":True,             # TV mode: hide the i3 / sway bar (the Quick Menu shows the time and status instead)
    "tv_keep_menu_open":True,       # TV mode: keep the Quick Menu on screen while no application is open
    "idle":{"screen_off":None,"lock":0,"sleep":0},   # seconds without input before each (0 never; screen_off None: the system decides), see power.py
    "hotkeys":DEFAULT_HOTKEYS,      # keyboard / remote / gamepad sets; deep-copied with the rest of the defaults
    "startup":{"mode":"none","profile_id":"","last_profile_id":""},   # mode: STARTUP_MODES
}
PIN_LAUNCH="launch"                  # the PIN is asked when the profile is launched
PIN_LAUNCH_AND_SHOW="launch_and_show"  # ... and when an open app of it is shown from a workspace that is not on screen
PIN_SCOPES=(PIN_LAUNCH,PIN_LAUNCH_AND_SHOW)
PIN_SCOPE_LABELS={PIN_LAUNCH:"Only when launching",PIN_LAUNCH_AND_SHOW:"When launching, and when showing it if it is open on a hidden workspace"}
MAX_DESCRIPTION=200

@dataclass
class LaunchProfile:
    id: str
    desktop_id: str
    name: str
    command: str = ""      # empty means use the desktop entry's standard launcher
    channel: int | None = None
    favorite: bool = False
    launch_mode: str = LAUNCH_SAME
    desktop_action: str = ""  # optional named Desktop Action from the .desktop file
    pin_hash: str = ""        # salted hash of the PIN that protects this profile ("" = unprotected)
    pin_scope: str = PIN_LAUNCH
    description: str = ""     # secondary profiles: replaces the default description (the launch options)
    hotkey: str = ""          # a hotkey spec (see hotkeys.py) that launches this profile ("" = none)

def _clean_text(value) -> str:
    return " ".join(str(value or "").split())[:MAX_DESCRIPTION]

def _clean_settings(raw) -> dict:
    s=copy.deepcopy(DEFAULT_SETTINGS)
    if not isinstance(raw,dict): return s
    for key,lo,hi in (("margin",0,200),("quick_width",320,900)):
        try:
            v=int(raw.get(key,s[key]))
            if lo<=v<=hi: s[key]=v
        except (TypeError,ValueError): pass
    accent=raw.get("accent")
    if isinstance(accent,str) and re.fullmatch(r"#[0-9a-fA-F]{6}",accent): s["accent"]=accent
    if isinstance(raw.get("lock_command"),str): s["lock_command"]=raw["lock_command"].strip()
    if raw.get("scale") in SCALE_PRESETS: s["scale"]=raw["scale"]
    if raw.get("use") in USES: s["use"]=raw["use"]
    for key in ("close_on_click_outside","open_in_new_workspace","always_new_workspace","hide_options_buttons","button_hints",
                "quick_settings_button","quick_close_button","quick_lock_button","update_prereleases",
                "clock_24h","tv_hide_bar","tv_keep_menu_open"):
        if isinstance(raw.get(key),bool): s[key]=raw[key]
    s["hotkeys"]=clean_hotkeys(raw.get("hotkeys"))
    s["idle"]=clean_idle(raw.get("idle"))
    st=raw.get("startup")
    if isinstance(st,dict):
        if st.get("mode") in STARTUP_MODES: s["startup"]["mode"]=st["mode"]
        for key in ("profile_id","last_profile_id"):
            if isinstance(st.get(key),str): s["startup"][key]=st[key]
        if st.get("show_menu") is True and s["startup"]["mode"]=="none": s["startup"]["mode"]="menu"   # before 2.11 the menu was a separate switch
    return s

class ConfigStore:
    def __init__(self, path: Path | str = DEFAULT_CONFIG):
        self.path=Path(path); self.profiles: list[LaunchProfile]=[]; self.settings=copy.deepcopy(DEFAULT_SETTINGS); self.app_descriptions: dict[str,str]={}
        self.load()
    def load(self):
        self.profiles=[]; self.settings=copy.deepcopy(DEFAULT_SETTINGS); self.app_descriptions={}
        try: data=json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError): return
        if not isinstance(data,dict): return
        self.settings=_clean_settings(data.get("settings"))
        raw_descriptions=data.get("app_descriptions")
        if isinstance(raw_descriptions,dict):
            self.app_descriptions={str(k):_clean_text(v) for k,v in raw_descriptions.items() if _clean_text(v)}
        for raw in data.get("profiles",[]):
            try:
                channel=raw.get("channel")
                channel=int(channel) if channel not in (None, "") else None
                if channel is not None and not 1 <= channel <= 999: channel=None
                # Files written before 2.3 have a boolean "tile" and no launch_mode; they load as LAUNCH_SAME.
                mode=raw.get("launch_mode")
                if mode not in LAUNCH_MODES: mode=LAUNCH_SAME
                self.profiles.append(LaunchProfile(str(raw.get("id") or uuid.uuid4()),str(raw["desktop_id"]),str(raw.get("name") or "Launch"),str(raw.get("command") or ""),channel,bool(raw.get("favorite",False)),mode,str(raw.get("desktop_action") or ""),
                                                  raw["pin_hash"] if valid_hash(raw.get("pin_hash")) else "",raw["pin_scope"] if raw.get("pin_scope") in PIN_SCOPES else PIN_LAUNCH,_clean_text(raw.get("description")),
                                                  raw["hotkey"] if isinstance(raw.get("hotkey"),str) and valid_spec(raw["hotkey"]) else ""))
            except (KeyError, TypeError, ValueError, AttributeError): continue
        self._deduplicate_channels(); self._deduplicate_hotkeys()
    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix(".json.tmp")
        temp.write_text(json.dumps({"version":2,"settings":self.settings,"app_descriptions":self.app_descriptions,"profiles":[asdict(p) for p in self.profiles]},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        os.replace(temp,self.path)
    def ensure_defaults(self, applications):
        known={p.desktop_id for p in self.profiles}
        changed=False
        for app in applications:
            if app.desktop_id not in known:
                self.profiles.append(LaunchProfile(str(uuid.uuid4()),app.desktop_id,app.name)); known.add(app.desktop_id); changed=True
        if changed: self.save()
    def get(self, profile_id):
        return next((p for p in self.profiles if p.id==profile_id),None)
    def for_app(self, desktop_id):
        return sorted((p for p in self.profiles if p.desktop_id==desktop_id),key=lambda p:(p.channel is None,p.channel or 0,p.name.casefold()))
    def assigned(self): return sorted((p for p in self.profiles if p.channel is not None),key=lambda p:(p.channel,p.name.casefold()))
    def favorites(self): return sorted((p for p in self.profiles if p.favorite),key=lambda p:(p.channel is None,p.channel or 0,p.name.casefold()))
    def set_profile(self, profile: LaunchProfile):
        if profile.channel is not None:
            if not 1 <= int(profile.channel) <= 999: raise ValueError("Channel must be between 1 and 999.")
            for other in self.profiles:
                if other.id != profile.id and other.channel == profile.channel:
                    raise ValueError(f"Channel {profile.channel} is already assigned to {other.name}.")
        if profile.launch_mode not in LAUNCH_MODES: raise ValueError("Unknown launch mode.")
        if profile.pin_scope not in PIN_SCOPES: raise ValueError("Unknown PIN scope.")
        if profile.pin_hash and not valid_hash(profile.pin_hash): raise ValueError("The PIN is not stored in a valid form.")
        if profile.hotkey and not valid_spec(profile.hotkey): raise ValueError("The hotkey is not valid.")
        profile.description=_clean_text(profile.description)
        profile.name=profile.name.strip()
        if not profile.name: raise ValueError("Profile name cannot be empty.")
        if profile.command.strip():
            try: parts=shlex.split(profile.command)
            except ValueError as exc: raise ValueError(f"Command quoting is invalid: {exc}")
            if not parts: raise ValueError("Custom command cannot be empty.")
        # A key does one thing: the editor has already asked before taking a hotkey from somewhere else.
        if profile.hotkey: self._release_hotkey(profile.hotkey,("profile",profile.id))
        for i,p in enumerate(self.profiles):
            if p.id==profile.id: self.profiles[i]=profile; break
        else: self.profiles.append(profile)
        self.save()
    def toggle_launch_mode(self, profile_id):
        """Flip a profile between 'same workspace (tiled)' and 'own new workspace'. Returns the new mode."""
        p=self.get(profile_id)
        if p is None: return None
        p.launch_mode=LAUNCH_SAME if p.launch_mode==LAUNCH_NEW_WORKSPACE else LAUNCH_NEW_WORKSPACE
        self.save(); return p.launch_mode
    def save_settings(self): self.save()
    def set_app_description(self, desktop_id, text):
        """Override an application's description in the Guide. Empty restores the one from its .desktop file."""
        text=_clean_text(text)
        if text: self.app_descriptions[desktop_id]=text
        else: self.app_descriptions.pop(desktop_id,None)
        self.save()
    def record_last_profile(self, profile_id):
        if self.settings["startup"]["last_profile_id"]!=profile_id:
            self.settings["startup"]["last_profile_id"]=profile_id; self.save()
    def delete(self, profile_id):
        self.profiles=[p for p in self.profiles if p.id!=profile_id]; self.save()
    # ---- hotkeys. Every hotkey has one owner: a device slot ("slot", device, action) or a profile ("profile", id).
    def hotkey_owner(self, spec, skip=None):
        """The owner of `spec` other than `skip`, or None when the key is free."""
        if not spec: return None
        for d,a,s in assigned(self.settings["hotkeys"]):
            if s==spec and ("slot",d,a)!=skip: return ("slot",d,a)
        return next((("profile",p.id) for p in self.profiles if p.hotkey==spec and ("profile",p.id)!=skip),None)
    def owner_label(self, owner) -> str:
        if owner is None: return ""
        if owner[0]=="slot": return f"{DEVICE_LABELS[owner[1]]}: {ACTION_LABELS[owner[2]]}"
        p=self.get(owner[1]); return p.name if p else "an application"
    def _release_hotkey(self, spec, keep):
        """Take `spec` away from every owner but `keep` (not saved)."""
        for d,a,s in assigned(self.settings["hotkeys"]):
            if s==spec and ("slot",d,a)!=keep: self.settings["hotkeys"][d][a]=""
        for p in self.profiles:
            if p.hotkey==spec and ("profile",p.id)!=keep: p.hotkey=""
    def set_slot_hotkey(self, device, action, spec):
        """Set (or, with "", clear) a device's hotkey, taking the key from whatever had it."""
        if spec: self._release_hotkey(spec,("slot",device,action))
        self.settings["hotkeys"][device][action]=spec; self.save()
    def set_profile_hotkey(self, profile_id, spec):
        """Set (or, with "", clear) a profile's hotkey, taking the key from whatever had it."""
        p=self.get(profile_id)
        if p is None: return
        if spec:
            if not valid_spec(spec): raise ValueError("The hotkey is not valid.")
            self._release_hotkey(spec,("profile",p.id))
        p.hotkey=spec; self.save()
    def hotkey_profiles(self):
        """Profiles that have a hotkey, by name."""
        return sorted((p for p in self.profiles if p.hotkey),key=lambda p:p.name.casefold())
    def app_hotkeys(self):
        """(spec, profile id, name) of every profile hotkey, for hotkeys.render_i3."""
        return [(p.hotkey,p.id,p.name) for p in self.hotkey_profiles()]
    def _deduplicate_hotkeys(self):
        """A profile cannot have a key a device slot or an earlier profile already has (only a hand-edited file does that)."""
        seen={s for _d,_a,s in assigned(self.settings["hotkeys"])}
        for p in sorted(self.profiles,key=lambda p:p.id):
            if p.hotkey:
                if p.hotkey in seen: p.hotkey=""
                else: seen.add(p.hotkey)

    def _deduplicate_channels(self):
        seen=set()
        for p in sorted(self.profiles,key=lambda p:p.id):
            if p.channel is not None:
                if p.channel in seen: p.channel=None
                else: seen.add(p.channel)

# ---------------------------------------------------------------- layout

@dataclass(frozen=True)
class Layout:
    """Pixel geometry of the TVWCS window (absolute screen coordinates) and of the panels inside it."""
    x: int
    y: int
    width: int
    height: int
    quick_width: int
    margin: int
    guide_open: bool
    @property
    def guide_width(self) -> int:
        return 0 if not self.guide_open else max(0,self.width-self.quick_width-self.margin)

def compute_layout(area, margin, quick_width, guide_open, options_open=False) -> Layout:
    """Panels left to right: Quick Menu | Applications (tabbed), each pair separated by one `margin`.
    The Quick Menu sits at the left of `area` (the usable workspace rectangle) with `margin` px above,
    below and to its left. The tabbed Applications pane fills the rest; Settings is a tab inside it, so
    the window no longer grows when it opens. The window spans only what is open. `options_open` is
    accepted for compatibility with older callers and ignored."""
    ax,ay,aw,ah=(int(area[k]) for k in ("x","y","width","height"))
    margin=max(0,min(int(margin),aw//4,ah//4))
    full=max(1,aw-2*margin); height=max(1,ah-2*margin)
    qw=max(1,min(int(quick_width),int(full*0.45)))
    return Layout(ax+margin,ay+margin,full if guide_open else qw,height,qw,margin,bool(guide_open))

# ---------------------------------------------------------------- badges

_BADGE_PATTERNS=(re.compile(r"^\s*\((\d{1,4})\+?\)\s*"),re.compile(r"^\s*\[(\d{1,4})\]\s*"))

def extract_badge(title, urgent=False):
    """Return (display_title, badge_text_or_None). Many apps (mail, chat) put an unread count at
    the start of the window title, e.g. '(3) Inbox'; i3 also flags windows as urgent."""
    t=title or ""
    for pattern in _BADGE_PATTERNS:
        m=pattern.match(t)
        if m:
            n=int(m.group(1)); clean=t[m.end():].strip() or t
            if n==0: return clean,("!" if urgent else None)
            return clean,("99+" if n>99 else str(n))
    return t,("!" if urgent else None)

# ---------------------------------------------------------------- search

def search_items(query, profiles, applications, windows):
    """Return tagged search results as dictionaries; search is case-insensitive."""
    q=(query or "").strip().casefold()
    results=[]
    def window_result(w):
        title,badge=extract_badge(w.get("title",""),w.get("urgent",False))
        return {"kind":"window","id":str(w.get('con_id')),"label":title or w.get("class") or "Untitled window","detail":"Open window","window":w,"badge":badge}
    if q.isdigit():
        number=int(q)
        for p in profiles:
            if p.channel==number:
                a=applications.get(p.desktop_id)
                results.append({"kind":"profile","id":p.id,"label":f"{p.channel:03d}  {p.name}","detail":a.name if a else p.desktop_id,"profile":p})
    else:
        for p in profiles:
            a=applications.get(p.desktop_id)
            label=p.name
            detail=(a.name if a else p.desktop_id)
            hay=" ".join([label,detail,p.desktop_id,p.command]).casefold()
            if not q or q in hay:
                results.append({"kind":"profile","id":p.id,"label":(f"{p.channel:03d}  " if p.channel is not None else "")+label,"detail":detail,"profile":p})
        for w in windows:
            hay=f"{w.get('title','')} {w.get('class','')} {w.get('instance','')}".casefold()
            if not q or q in hay: results.append(window_result(w))
    # Profiles first, then windows; channel numbers before unassigned profiles.
    results.sort(key=lambda r:(0 if r["kind"]=="profile" else 1, r.get("profile").channel is None if r["kind"]=="profile" else False, r.get("profile").channel or 0 if r["kind"]=="profile" else 0, r["label"].casefold()))
    return results[:80]


def profile_detail(profile, app) -> str:
    """The launch options of a secondary profile: the chosen .desktop action and any custom launch command."""
    parts=[]
    if profile.desktop_action:
        names=dict(app.desktop_actions) if app else {}
        parts.append(names.get(profile.desktop_action,profile.desktop_action))
    if profile.command.strip(): parts.append(profile.command.strip())
    return "  ·  ".join(parts)

def row_description(profile, app, primary, app_override="") -> str:
    """The description shown beside a profile's name. A main profile shows its application's description (the user's
    override, else the .desktop file's); a secondary profile shows its own override, else its launch options."""
    if primary: return app_override or ((app.comment or app.generic_name) if app else "") or ""
    return profile.description.strip() or profile_detail(profile,app)

def startup_choices(profiles):
    """Applications to offer for 'open at login', most likely first: favorites, then channels, then everything else."""
    by_number=lambda p:(p.channel is None,p.channel or 0,p.name.casefold())
    favorites=sorted((p for p in profiles if p.favorite),key=by_number)
    channels=sorted((p for p in profiles if p.channel is not None and not p.favorite),key=by_number)
    others=sorted((p for p in profiles if not p.favorite and p.channel is None),key=lambda p:p.name.casefold())
    return [(title,group) for title,group in (("FAVORITES",favorites),("CHANNELS",channels),("ALL OTHER APPS",others)) if group]
