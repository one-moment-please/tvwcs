"""TVWCS preferences, profiles, layout maths and search helpers; no GTK dependency."""
from __future__ import annotations
import copy, json, os, re, shlex, uuid
from dataclasses import dataclass, asdict
from pathlib import Path

from tvwcs.hotkeys import ACTION_LABELS, DEFAULT_HOTKEYS, DEVICE_LABELS, assigned, clean_hotkeys, valid_spec
from tvwcs.pinlock import valid_hash
from tvwcs.power import clean_critical, clean_idle

CONFIG_HOME=Path(os.environ.get("XDG_CONFIG_HOME",str(Path.home()/".config")))
DEFAULT_CONFIG=CONFIG_HOME/"tvwcs"/"config.json"

# How a profile is placed when launched or when its open window is selected.
LAUNCH_SAME="same"                  # tile alongside whatever is on the current workspace
LAUNCH_NEW_WORKSPACE="new_workspace"  # always get a workspace of its own
LAUNCH_MODES=(LAUNCH_SAME,LAUNCH_NEW_WORKSPACE)
LAUNCH_PLAIN="plain"                # desktop mode: as sway places it (opened where it opens, focused where it is)

# TVWCS's own windows are recognised by title. The prefix is deliberately unusual: a document called
# "tvwcs notes" in a text editor must never be mistaken for one of them (it would vanish from Open applications).
MAIN_TITLE="TVWCS"
DIALOG_PREFIX="TVWCS · "
def is_tvwcs_title(title: str) -> bool:
    return title==MAIN_TITLE or (title or "").startswith(DIALOG_PREFIX)

# TV mode and desktop mode. TVWCS runs in TV mode in a TVWCS session (the login screen's "TVWCS", whose tvwcs-session
# wrapper exports TVWCS_SESSION), and in desktop mode in any other sway session (TVWCS included in the usual sway
# config). In TV mode apps open full screen in workspaces of their own, the bar is hidden, the Quick Menu stays open
# while nothing is, the mouse pointer hides when it rests and TVWCS's lock screen is used. In desktop mode sway places
# apps as it always does and TVWCS changes nothing about the bar, the pointer or locking.
# TVWCS_MODE=tv|desktop overrides it (for trying one mode in the other's session, and for the tests).
def tv_mode(env=None) -> bool:
    env=os.environ if env is None else env
    forced=env.get("TVWCS_MODE")
    if forced in ("tv","desktop"): return forced=="tv"
    return bool(env.get("TVWCS_SESSION"))

SCALE_PRESETS={"desktop":1.0,"tenfoot":1.6,"tenfoot_4k":3.0}
SCALE_LABELS={"desktop":"Desktop","tenfoot":"TV Mode","tenfoot_4k":"4K TV Mode"}
AUTO_SCALE={True:"tenfoot",False:"desktop"}   # the interface size when none is chosen ("scale": ""): by the mode
def scale_key(settings, tv=None) -> str:
    """The interface size in use: the one chosen, else TV Mode in TV mode and Desktop in desktop mode."""
    key=settings.get("scale") or ""
    return key if key in SCALE_PRESETS else AUTO_SCALE[tv_mode() if tv is None else tv]
# The screen height each TV size is drawn for. On a smaller screen (a 720p TV) it shrinks to fit, never below Desktop.
SCALE_DESIGN_HEIGHT={"tenfoot":1080,"tenfoot_4k":2160}
def effective_scale(key, screen_height=0) -> float:
    """The interface size actually used: the preset, made smaller on a screen shorter than the one it is drawn for."""
    scale=SCALE_PRESETS.get(key,1.0); design=SCALE_DESIGN_HEIGHT.get(key)
    if design and screen_height and screen_height<design: scale=max(1.0,round(scale*screen_height/design,3))
    return scale
UHD_SCALES=("tenfoot_4k",)   # only offered when a 4K (3840×2160) or larger display is connected

def scale_choices(current, has_4k_display, tv=None):
    """The interface sizes to offer: Automatic (by the mode), then the sizes; 4K TV Mode needs a 4K display, unless it
    is the one already chosen."""
    auto=SCALE_LABELS[AUTO_SCALE[tv_mode() if tv is None else tv]]
    return [("",f"Automatic ({auto} in this mode)")]+[(k,v) for k,v in SCALE_LABELS.items() if has_4k_display or k not in UHD_SCALES or k==current]

def is_4k(width, height) -> bool:
    return max(width,height)>=3840 and min(width,height)>=2160
STARTUP_MODES=("none","last","app")
STARTUP_LABELS={"none":"None","last":"Last application","app":"Chosen application"}

# Settings > Appearance > Accent colour: the Metro colours of widgets.METRO_COLORS, by name (a hand-set colour keeps its hex).
ACCENT_NAMES={"#0078d7":"Blue","#e81123":"Red","#00b294":"Teal","#ff8c00":"Orange","#881798":"Purple","#107c10":"Green",
              "#ea005e":"Magenta","#6b69d6":"Iris","#00cc6a":"Mint","#c239b3":"Orchid"}
def accent_name(colour) -> str: return ACCENT_NAMES.get((colour or "").lower(),colour or "")
# Settings > Appearance > Screen edge margin, in px at desktop scale: many TVs crop the picture's edges (overscan).
MARGIN_RANGE=(0,120)
# Channels run from 000 to 999. Channel 000 goes to TVWCS's own Settings app, once, on a new or updated install.
CHANNEL_MIN,CHANNEL_MAX=0,999
SETTINGS_DESKTOP_ID="com.tvwcs.ControlPanel.desktop"
# Settings > Appearance > Theme: TVWCS's light or dark look; applications that follow the desktop's colour scheme follow it.
THEMES={"dark":"Dark","light":"Light"}
# Settings > Appearance > Background colour: what shows where no application is open, and behind the Quick Menu.
# Six greys from white to black, six bright colours and the same six darkened. Shown as swatches without names.
WALLPAPER_GREYS=("#ffffff","#c8c8c8","#969696","#646464","#323232","#000000")
WALLPAPER_COLOURS=("#e81123","#ff8c00","#ffd800","#107c10","#0078d7","#881798")
WALLPAPER_DARK=("#740912","#804600","#806c00","#083e08","#003c6c","#440c4c")
WALLPAPERS=WALLPAPER_GREYS+WALLPAPER_COLOURS+WALLPAPER_DARK
DEFAULT_WALLPAPER="#323232"   # dark grey
# The on-screen keyboard: hidden (a button shows it), the full keyboard, or a number pad. The one last used comes back.
KEYBOARDS={"hidden":"Hidden","full":"Full keyboard","digits":"Number pad"}

def key_hints(tv) -> str:
    """The Settings app's footer: a remote's key is called Back, a keyboard's Esc."""
    back="Back" if tv else "Esc"
    return f"↑ ↓ ← →  Navigate    {'OK' if tv else 'Enter'}  Select\n{back}  Go back"

DEFAULT_SETTINGS={
    "margin":0,                     # px (at desktop scale) between the panels and the edges of the usable workspace
    "quick_width":460,              # px (at desktop scale) width of the Quick Menu; the Settings panel matches it
    "accent":"#0078d7",             # Metro accent colour
    "lock_command":"",              # empty = auto-detect a screen locker (desktop mode; TV mode uses TVWCS's lock screen)
    "scale":"",                     # key of SCALE_PRESETS, or "" for the mode's own size (scale_key)
    "close_on_click_outside":True,  # close TVWCS when it loses focus (another window takes it)
    "update_prereleases":False,     # TVWCS's updater also offers prereleases (releases not yet tested and marked latest)
    "clock_24h":False,              # the Quick Menu's clock shows 14:05 instead of 2:05 PM
    "theme":"dark",                 # THEMES: TVWCS's look, passed on to applications that follow the desktop's colour scheme
    "wallpaper":DEFAULT_WALLPAPER,  # WALLPAPERS: the background where no application is open
    "keyboard":"hidden",            # KEYBOARDS: the on-screen keyboard as it was last left (hidden, full or the number pad)
    "channel_zero_done":False,      # channel 000 has been given to Settings (once; afterwards it is the user's)
    "audio_boost":False,            # Settings > Sound: volumes may go over 100% (else they stop there)
    "idle":{"screen_off":0,"lock":0,"sleep":0},   # seconds without input before each (0 never), see power.py
    "idle_battery":{"screen_off":0,"lock":0,"sleep":0},   # the same, while a laptop runs on its battery
    "battery_critical":{"action":"shutdown","percent":5},   # what to do when the battery is nearly empty (power.CRITICAL_ACTIONS)
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
    for key,lo,hi in (("margin",*MARGIN_RANGE),("quick_width",320,900)):
        try:
            v=int(raw.get(key,s[key]))
            if lo<=v<=hi: s[key]=v
        except (TypeError,ValueError): pass
    accent=raw.get("accent")
    if isinstance(accent,str) and re.fullmatch(r"#[0-9a-fA-F]{6}",accent): s["accent"]=accent
    if isinstance(raw.get("lock_command"),str): s["lock_command"]=raw["lock_command"].strip()
    if raw.get("scale") in SCALE_PRESETS: s["scale"]=raw["scale"]
    # Before 4.0, "Used on" (use) set the size along with it: a size that only followed it now follows the mode
    if raw.get("use") in ("tv","desktop") and raw.get("scale")==AUTO_SCALE[raw["use"]=="tv"]: s["scale"]=""
    if raw.get("theme") in THEMES: s["theme"]=raw["theme"]
    if isinstance(raw.get("wallpaper"),str) and raw["wallpaper"].lower() in WALLPAPERS: s["wallpaper"]=raw["wallpaper"].lower()
    if raw.get("keyboard") in KEYBOARDS: s["keyboard"]=raw["keyboard"]
    for key in ("close_on_click_outside","update_prereleases","clock_24h","channel_zero_done",
                "audio_boost"):
        if isinstance(raw.get(key),bool): s[key]=raw[key]
    s["hotkeys"]=clean_hotkeys(raw.get("hotkeys"))
    s["idle"]=clean_idle(raw.get("idle")); s["idle_battery"]=clean_idle(raw.get("idle_battery"))
    s["battery_critical"]=clean_critical(raw.get("battery_critical"))
    st=raw.get("startup")
    if isinstance(st,dict):
        if st.get("mode") in STARTUP_MODES: s["startup"]["mode"]=st["mode"]
        for key in ("profile_id","last_profile_id"):
            if isinstance(st.get(key),str): s["startup"][key]=st[key]
    return s

# Names TVWCS's own Settings entry had before its .desktop file was renamed (profiles made then still carry them).
LEGACY_NAMES_ALL={"com.tvwcs.ControlPanel.desktop":("Control Panel","Settings","TVWCS Settings")}
LEGACY_NAMES={k:v[0] for k,v in LEGACY_NAMES_ALL.items()}

class ConfigStore:
    def __init__(self, path: Path | str = DEFAULT_CONFIG):
        self.path=Path(path); self.profiles: list[LaunchProfile]=[]; self.settings=copy.deepcopy(DEFAULT_SETTINGS); self.app_descriptions: dict[str,str]={}
        self.app_names: dict[str,str]={}
        self.load()
    def load(self):
        self.profiles=[]; self.settings=copy.deepcopy(DEFAULT_SETTINGS); self.app_descriptions={}; self.app_names={}
        try: data=json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError): return
        if not isinstance(data,dict): return
        self.settings=_clean_settings(data.get("settings"))
        raw_descriptions=data.get("app_descriptions")
        if isinstance(raw_descriptions,dict):
            self.app_descriptions={str(k):_clean_text(v) for k,v in raw_descriptions.items() if _clean_text(v)}
        raw_names=data.get("app_names")
        if isinstance(raw_names,dict): self.app_names={str(k):str(v) for k,v in raw_names.items() if isinstance(v,str)}
        for raw in data.get("profiles",[]):
            try:
                channel=raw.get("channel")
                channel=int(channel) if channel not in (None, "") else None
                if channel is not None and not CHANNEL_MIN <= channel <= CHANNEL_MAX: channel=None
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
        temp.write_text(json.dumps({"version":2,"settings":self.settings,"app_descriptions":self.app_descriptions,"app_names":self.app_names,"profiles":[asdict(p) for p in self.profiles]},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        os.replace(temp,self.path)
    def ensure_defaults(self, applications):
        """Give every application a launch profile, and keep a plain profile's name in step when the application is
        renamed (its .desktop file now has another Name): a name the user typed is left alone."""
        known={p.desktop_id for p in self.profiles}
        changed=False
        for app in applications:
            old=self.app_names.get(app.desktop_id) or LEGACY_NAMES.get(app.desktop_id)
            if self.app_names.get(app.desktop_id)!=app.name: self.app_names[app.desktop_id]=app.name; changed=True
            for p in self.profiles:
                if p.desktop_id==app.desktop_id and p.name!=app.name and not p.command and not p.desktop_action \
                        and (p.name==old or p.name in LEGACY_NAMES_ALL.get(app.desktop_id,())):
                    p.name=app.name; changed=True
            if app.desktop_id not in known:
                self.profiles.append(LaunchProfile(str(uuid.uuid4()),app.desktop_id,app.name)); known.add(app.desktop_id); changed=True
            if app.desktop_id in self.app_descriptions:   # before 4.0 an application had one description: its default profile's now
                main=default_of(self.for_app(app.desktop_id),app.name); text=self.app_descriptions.pop(app.desktop_id); changed=True
                if main is not None and not main.description: main.description=text
        if self._give_settings_channel_zero(): changed=True
        if changed: self.save()
    def _give_settings_channel_zero(self):
        """Channel 000 opens Settings: given once (a new install, or the first start after updating to 3.1), to the
        Settings app's main profile, when no other profile has it. The user may change it afterwards."""
        if self.settings["channel_zero_done"]: return False
        main=next((p for p in self.for_app(SETTINGS_DESKTOP_ID) if not p.command and not p.desktop_action),None)
        if main is None: return False   # Settings is not installed (yet): try again next time
        if not any(p.channel==0 for p in self.profiles): main.channel=0
        self.settings["channel_zero_done"]=True; return True
    def get(self, profile_id):
        return next((p for p in self.profiles if p.id==profile_id),None)
    def for_app(self, desktop_id):
        return sorted((p for p in self.profiles if p.desktop_id==desktop_id),key=lambda p:(p.channel is None,p.channel or 0,p.name.casefold()))
    def assigned(self): return sorted((p for p in self.profiles if p.channel is not None),key=lambda p:(p.channel,p.name.casefold()))
    def favorites(self): return sorted((p for p in self.profiles if p.favorite),key=lambda p:(p.channel is None,p.channel or 0,p.name.casefold()))
    def set_profile(self, profile: LaunchProfile):
        if profile.channel is not None:
            if not CHANNEL_MIN <= int(profile.channel) <= CHANNEL_MAX: raise ValueError("The channel must be from 000 to 999.")
            for other in self.profiles:
                if other.id != profile.id and other.channel == profile.channel:
                    raise ValueError(f"Channel {profile.channel} is already assigned to {other.name}.")
        if profile.launch_mode not in LAUNCH_MODES: raise ValueError("Unknown launch mode.")
        if profile.pin_scope not in PIN_SCOPES: raise ValueError("Unknown PIN scope.")
        if profile.pin_hash and not valid_hash(profile.pin_hash): raise ValueError("The PIN is not stored in a valid form.")
        if profile.hotkey and not valid_spec(profile.hotkey): raise ValueError("The hotkey is not valid.")
        profile.description=_clean_text(profile.description)
        profile.name=profile.name.strip()
        if not profile.name: raise ValueError("The name cannot be empty.")
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
        """Override an application's description in Applications. Empty restores the one from its .desktop file."""
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
        """(spec, profile id, name) of every profile hotkey, for hotkeys.render_bindings."""
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

def compute_layout(area, margin, quick_width, guide_open, options_open=False, guide_width=None, quick_height=None) -> Layout:
    """Panels left to right: Quick Menu | Applications (tabbed), each pair separated by one `margin`.
    The Quick Menu sits at the left of `area` (the usable workspace rectangle) with `margin` px above,
    below and to its left. The tabbed Applications pane fills the rest; Settings is a tab inside it, so
    the window no longer grows when it opens. The window spans only what is open. `options_open` is
    accepted for compatibility with older callers and ignored. `guide_width` (desktop use) caps the Applications pane
    at what its contents need, so the window does not fill the screen. `quick_height` (desktop use, Applications closed)
    shrinks the Quick Menu to what its contents need, kept in the bottom-left corner with the same margins."""
    ax,ay,aw,ah=(int(area[k]) for k in ("x","y","width","height"))
    margin=max(0,min(int(margin),aw//4,ah//4))
    full=max(1,aw-2*margin); height=max(1,ah-2*margin)
    qw=max(1,min(int(quick_width),int(full*0.45)))
    width=full
    if guide_width: width=max(qw+margin+1,min(full,qw+margin+int(guide_width)))
    if quick_height and not guide_open:
        h=max(1,min(height,int(quick_height)))
        return Layout(ax+margin,ay+ah-margin-h,qw,h,qw,margin,False)
    return Layout(ax+margin,ay+margin,width if guide_open else qw,height,qw,margin,bool(guide_open))

# ---------------------------------------------------------------- badges

_BADGE_PATTERNS=(re.compile(r"^\s*\((\d{1,4})\+?\)\s*"),re.compile(r"^\s*\[(\d{1,4})\]\s*"))

def extract_badge(title, urgent=False):
    """Return (display_title, badge_text_or_None). Many apps (mail, chat) put an unread count at
    the start of the window title, e.g. '(3) Inbox'; sway also flags windows as urgent."""
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
    # A profile whose application was uninstalled cannot start (unless it runs its own command): it is not offered.
    profiles=[p for p in profiles if p.desktop_id in applications or p.command.strip()]
    def window_result(w):
        title,badge=extract_badge(w.get("title",""),w.get("urgent",False))
        return {"kind":"window","id":str(w.get('con_id')),"label":title or w.get("class") or "Untitled window","detail":"Open window","window":w,"badge":badge}
    def detail_of(p, a):   # the application's name when the profile has another, else what the application is
        if not a: return p.desktop_id
        return a.name if a.name!=p.name else (a.generic_name or a.comment or "")
    if q.isdigit():
        number=int(q)
        for p in profiles:
            if p.channel==number:
                a=applications.get(p.desktop_id)
                results.append({"kind":"profile","id":p.id,"label":f"{p.channel:03d}  {p.name}","detail":detail_of(p,a),"profile":p})
    else:
        for p in profiles:
            a=applications.get(p.desktop_id)
            label=p.name
            detail=detail_of(p,a)
            hay=" ".join([label,a.name if a else "",detail,p.desktop_id,p.command]).casefold()
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
    """The description shown beside a profile's name: each profile has its own (4.0). Without one, the default
    profile shows its application's (the .desktop file's), another profile its launch options. `app_override` is the
    one description per application from before 4.0, for a default profile that has none yet."""
    if profile.description.strip(): return profile.description.strip()
    if primary: return app_override or ((app.comment or app.generic_name) if app else "") or ""
    return profile_detail(profile,app)

# ---------------------------------------------------------------- profile names
DEFAULT_LABEL="Default"   # the default profile's name: never shown, never changed
def default_of(profiles, app_name):
    """An application's default profile among its `profiles`: the plain one (no command or desktop action) with the
    application's name, else the first plain one, else the first."""
    plain=[p for p in profiles if not p.command and not p.desktop_action]
    return next((p for p in plain if p.name==app_name),(plain or list(profiles) or [None])[0])

def profile_label(profile, app_name, primary) -> str:
    """A profile's own name, without the application's: "Default" for the default profile; for a profile named
    before 4.0 with the application's name in front ("Kodi profile 2"), what follows it."""
    if primary: return DEFAULT_LABEL
    name=profile.name.strip()
    if app_name and name.casefold().startswith(app_name.casefold()+" "): return name[len(app_name)+1:].strip() or name
    return name

def display_name(profile, app_name, primary) -> str:
    """The name shown in lists: the application's name, which is never changed, with the profile's name after it
    (none for the default profile)."""
    if not app_name: return profile.name
    return app_name if primary else f"{app_name} {profile_label(profile,app_name,False)}"

def next_label(labels) -> str:
    """A new profile's name: the first number from 2 that no other profile of the application has."""
    taken={str(l).strip().casefold() for l in labels}; n=2
    while str(n) in taken: n+=1
    return str(n)

def startup_choices(profiles):
    """Applications to offer for 'open at login', most likely first: favorites, then channels, then everything else."""
    by_number=lambda p:(p.channel is None,p.channel or 0,p.name.casefold())
    favorites=sorted((p for p in profiles if p.favorite),key=by_number)
    channels=sorted((p for p in profiles if p.channel is not None and not p.favorite),key=by_number)
    others=sorted((p for p in profiles if not p.favorite and p.channel is None),key=lambda p:p.name.casefold())
    return [(title,group) for title,group in (("FAVORITES",favorites),("CHANNELS",channels),("ALL OTHER APPS",others)) if group]
