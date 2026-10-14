"""The Control Panel's pages. Each reads the system on a worker thread (control_* modules), then draws its rows;
a page that is on screen re-reads quietly every few seconds and only redraws when something changed, keeping the
selection on the same row."""
from __future__ import annotations
import os, time
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango

from tvwcs import control_bluetooth as bluetooth, control_display as display, control_network as network, control_sound as sound, control_sysinfo as sysinfo, control_updates as updates
from tvwcs import privilege
from tvwcs.system_actions import command_for
from tvwcs.ui_control import StreamedRun, in_background
from tvwcs.widgets import NavGroup, S, clear_box, glyph, muted_label, section_title, usable

try:
    gi.require_version("Vte","3.91")
    from gi.repository import Vte
except (ImportError,ValueError):
    Vte=None

class Page:
    key=""; title=""; icon=""; fallback=""
    poll=0              # seconds between quiet re-reads while the page is on screen (0: only when asked)
    refreshable=True    # a ⟳ button at the top right re-reads the page

    def __init__(self, win):
        self.win=win; self.state=None; self.busy=False; self.status=""; self._loaded=False; self._poll=0
        self.header=[]; self.groups=[]; self._ids={}; self.root=None

    # ---------------------------------------------------------- frame
    def widget(self):
        root=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0); self.root=root
        head=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(14)); head.set_margin_top(S(12)); head.set_margin_start(S(24)); head.set_margin_end(S(24)); head.set_margin_bottom(S(6))
        title=Gtk.Label(label=self.title); title.add_css_class("pane-title"); title.set_xalign(0); head.append(title)
        self.subtitle=Gtk.Label(); self.subtitle.add_css_class("muted"); self.subtitle.set_valign(Gtk.Align.END); self.subtitle.set_margin_bottom(S(6))
        self.subtitle.set_xalign(0); self.subtitle.set_hexpand(True); self.subtitle.set_ellipsize(Pango.EllipsizeMode.END); head.append(self.subtitle)
        if self.refreshable:
            b=Gtk.Button(); b.add_css_class("square"); b.set_valign(Gtk.Align.START); b.set_child(glyph("view-refresh-symbolic","⟳")); b.set_tooltip_text("Check again")
            b.connect("clicked",lambda *_:self.refresh()); head.append(b); self.header=[b]
        root.append(head); root.append(self.content()); return root

    def content(self):
        scroll=Gtk.ScrolledWindow(); scroll.set_vexpand(True); scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        self.body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4)); self.body.set_margin_start(S(24)); self.body.set_margin_end(S(24)); self.body.set_margin_bottom(S(16))
        scroll.set_child(self.body); return scroll

    def nav_groups(self):
        return ([NavGroup(self.header)] if self.header else [])+self.groups
    def captures_keys(self, focused): return False

    # ---------------------------------------------------------- reading
    def shown(self):
        if not self._loaded: self._loaded=True; self.refresh()
        if self.poll and not self._poll: self._poll=GLib.timeout_add_seconds(self.poll,self._tick)
    def hidden(self):
        if self._poll: GLib.source_remove(self._poll); self._poll=0
    def _tick(self):
        if not self.busy and not self.win.modal_open and self.win.is_visible(): self.refresh(quiet=True)
        return GLib.SOURCE_CONTINUE
    def read(self): return None
    def refresh(self, quiet=False):
        if self.busy: return
        self.busy=True
        if not quiet: self.set_status("Checking…")
        def done(state):
            self.busy=False
            if not quiet: self.set_status("")
            if quiet and state==self.state: return
            self.state=state; self.redraw()
        def failed(exc):
            self.busy=False; self.set_status(""); self.win.notice(f"{self.title}",f"Could not read the settings: {exc}")
        in_background(self.read,done,failed)
    def set_status(self, text):
        self.status=text; self.subtitle.set_text(text or self.summary())
    def summary(self): return ""

    def act(self, work, status, title, after=None):
        """Change something on a worker thread: work() returns "" when it worked, else why not, which is shown.
        The page is read again afterwards."""
        self.set_status(status)
        def done(problem):
            self.set_status("")
            if problem: self.win.notice(title,problem)
            if after: after()
            self.busy=False; self.refresh(quiet=True)
        def failed(exc): done(str(exc))
        self.busy=True; in_background(work,done,failed)

    # ---------------------------------------------------------- drawing
    def redraw(self):
        """Draw the rows again from self.state, keeping the selection on the same row (by its id)."""
        focused=self.win.get_focus(); old=None
        if focused is not None and self.root is not None and (focused is self.root or focused.is_ancestor(self.root)):
            old=next((i for i,w in self._ids.items() if w is focused or focused.is_ancestor(w)),None)
        stale={id(w):i for i,w in self._ids.items()}
        clear_box(self.body); self.groups=[]; self._ids={}
        self.draw(self.state); self.subtitle.set_text(self.status or self.summary())
        for widget_ref in ("_return_focus",):   # a dialog open over this page goes back to the row's new button
            w=getattr(self.win,widget_ref,None)
            if w is not None and id(w) in stale and stale[id(w)] in self._ids: setattr(self.win,widget_ref,self._ids[stale[id(w)]])
        last=self.win._last_page_focus.get(self.key)
        if last is not None and id(last) in stale and stale[id(last)] in self._ids: self.win._last_page_focus[self.key]=self._ids[stale[id(last)]]
        if old is not None:
            target=self._ids.get(old)
            if target is not None and usable(target): target.grab_focus()
            elif not self.win._focus_first(self.groups): self.win.tab_buttons[self.key].grab_focus()
    def draw(self, state): pass

    def add(self, widget): self.body.append(widget); return widget
    def section(self, text): return self.add(section_title(text))
    def note(self, text, css=None):
        l=muted_label(text)
        if css: l.add_css_class(css)
        return self.add(l)
    def register(self, *widgets, ident=None, column=False):
        g=NavGroup([w for w in widgets if w is not None]); g.column=column
        if g: self.groups.append(g)
        if ident is not None and g: self._ids[ident]=g[0]
        for k,w in enumerate(g[1:],1):
            if ident is not None: self._ids[f"{ident}#{k}"]=w
        return g

    def row(self, label, value="", on_activate=None, detail="", icon=None, fallback="", ident=None, extras=(), value_css="setting-value"):
        """One row: an optional icon, its name (and a detail line under it), its value on the right; square extra
        buttons follow it on the same row. ← / → move between them."""
        line=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(4))
        b=Gtk.Button(); b.add_css_class("launch-row"); b.set_hexpand(True)
        if on_activate is None: b.add_css_class("info-row")
        inner=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(14))
        if icon is not None or fallback:
            g=glyph(icon,fallback,24); g.set_size_request(S(32),-1); inner.append(g)
        text=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0); text.set_hexpand(True); text.set_valign(Gtk.Align.CENTER)
        name=Gtk.Label(label=label); name.set_xalign(0); name.set_ellipsize(Pango.EllipsizeMode.END); text.append(name)
        if detail:
            d=Gtk.Label(label=detail); d.add_css_class("row-detail"); d.set_xalign(0); d.set_ellipsize(Pango.EllipsizeMode.END); text.append(d)
        inner.append(text)
        if value:
            v=Gtk.Label(label=value); v.add_css_class(value_css); v.set_xalign(1); inner.append(v)
        b.set_child(inner)
        if on_activate is not None: b.connect("clicked",lambda *_:on_activate())
        line.append(b)
        extras=[e for e in extras if e is not None]
        for e in extras: e.add_css_class("square"); line.append(e)
        self.add(line); self.register(b,*extras,ident=ident); return b

    def button(self, icon, fallback, tooltip, handler, danger=False):
        b=Gtk.Button(); b.set_child(glyph(icon,fallback)); b.set_tooltip_text(tooltip); b.connect("clicked",lambda *_:handler())
        if danger: b.add_css_class("close-button")
        return b

def _on_off(flag): return "On" if flag else "Off"
def _outcome(result, otherwise):
    """A control_cmd.Result as act() wants it: "" when it worked, else why not."""
    return "" if result.ok else (result.message or otherwise)

# ====================================================================== Sound
class SoundPage(Page):
    key="sound"; title="Sound"; icon="audio-volume-high-symbolic"; fallback="🔊"; poll=3
    def read(self): return sound.read_state()
    def summary(self): return self.state.server if self.state and self.state.available else ""
    def draw(self, state):
        if not state.available: self.note(state.message); return
        self.section("OUTPUT")
        current=state.output()
        if current is None: self.note("No sound output was found.")
        else:
            self.volume_row(current,"out")
            for d in state.outputs: self.device_row(d,d.name==(current.name if current else ""),"audio-speakers-symbolic","🔈")
        self.section("INPUT")
        current=state.input()
        if current is None: self.note("No microphone or other input is connected.")
        else:
            self.volume_row(current,"in")
            for d in state.inputs: self.device_row(d,d.name==current.name,"audio-input-microphone-symbolic","🎤")
        self.note("Choosing a device uses it from now on; sound that is already playing moves to it too.")

    def device_row(self, d, in_use, icon, fallback):
        ports=[p for p in d.ports if p.available]
        port=next((p.label for p in d.ports if p.name==d.active_port),"")
        extra=None
        if len(ports)>1:
            extra=self.button("view-list-symbolic","⋯",f"Choose the connector of {d.label}",lambda d=d,ports=ports:self.choose_port(d,ports))
        self.row(d.label,"In use" if in_use else "",(lambda d=d:self.act(lambda:_outcome(sound.make_default(d),"Could not switch to that device."),
                 f"Switching to {d.label}…","Sound")) if not in_use else None,
                 detail=port if len(ports)>1 else "",icon=icon,fallback=fallback,ident=f"{d.kind}:{d.name}",extras=[extra],
                 value_css="state-on")

    def choose_port(self, d, ports):
        def picked(name): self.act(lambda:_outcome(sound.set_port(d,name),"Could not switch the connector."),"Switching…","Sound")
        self.win.choose_option(f"Connector · {d.label}",[(p.name,p.label) for p in ports],d.active_port,picked)

    def volume_row(self, d, ident):
        """− [ level ] + and mute. The bar can be dragged with a mouse; the D-pad uses − and +."""
        line=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(6)); line.set_margin_top(S(2)); line.set_margin_bottom(S(4))
        minus=self.button("list-remove-symbolic","−","Quieter",lambda:step(-1)); plus=self.button("list-add-symbolic","+","Louder",lambda:step(1))
        mute=Gtk.Button()
        scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,sound.MAX_VOLUME,1); scale.set_draw_value(False); scale.set_hexpand(True)
        scale.set_focusable(False); scale.set_valign(Gtk.Align.CENTER)
        value=Gtk.Label(); value.add_css_class("volume-value"); value.set_xalign(1)
        guard=[False]; pending=[0]
        def show():
            guard[0]=True; scale.set_value(d.volume); guard[0]=False
            value.set_text(f"{d.volume} %")
            (scale.add_css_class if d.muted else scale.remove_css_class)("muted")
            mute.set_child(glyph("audio-volume-muted-symbolic" if d.muted else "audio-volume-high-symbolic","🔇" if d.muted else "🔊"))
            mute.set_tooltip_text(("Unmute " if d.muted else "Mute ")+d.label)
            (mute.add_css_class if d.muted else mute.remove_css_class)("active")
        def apply_volume():
            pending[0]=0; level=d.volume; in_background(lambda:sound.set_volume(d,level),lambda _r:None); return GLib.SOURCE_REMOVE
        def step(direction):
            d.volume=sound.stepped(d.volume,direction); show()
            if pending[0]: GLib.source_remove(pending[0])
            pending[0]=GLib.timeout_add(120,apply_volume)   # holding the key sends one change, not twenty
        def dragged(*_):
            if guard[0]: return
            d.volume=int(scale.get_value()); value.set_text(f"{d.volume} %")
            if pending[0]: GLib.source_remove(pending[0])
            pending[0]=GLib.timeout_add(120,apply_volume)
        def toggle_mute():
            d.muted=not d.muted; show(); in_background(lambda:sound.set_muted(d,d.muted),lambda _r:None)
        scale.connect("value-changed",dragged); mute.connect("clicked",lambda *_:toggle_mute())
        for w in (minus,plus,mute): w.add_css_class("square")
        label=Gtk.Label(label="Volume"); label.set_xalign(0); label.set_size_request(S(110),-1)
        for w in (label,minus,scale,value,plus,mute): line.append(w)
        show(); self.add(line); self.register(minus,plus,mute,ident=f"volume:{ident}")

# ====================================================================== Displays
class DisplaysPage(Page):
    """Resolution and refresh rate of each display; with several, which are on, where each one is and (X11) the
    primary one. A change that can leave a screen blank goes back by itself unless it is kept."""
    key="displays"; title="Displays"; icon="video-display-symbolic"; fallback="🖵"; poll=5
    KEEP_SECONDS=15
    def read(self):
        s=display.read_state()
        if s.available:
            names=self.monitor_names()
            for o in s.outputs: o.label=o.label or names.get(o.name,"")
        return s
    def monitor_names(self):
        """Connector -> the display's own name, from GDK (it reads the displays' EDID on X11)."""
        gd=Gdk.Display.get_default(); monitors=gd.get_monitors() if gd else None; names={}
        for i in range(monitors.get_n_items() if monitors is not None else 0):
            m=monitors.get_item(i); label=" ".join(x for x in ((m.get_manufacturer() or ""),(m.get_model() or "")) if x).strip()
            if m.get_connector() and label: names[m.get_connector()]=label
        return names
    def summary(self):
        s=self.state
        if not s or not s.available: return ""
        n=len(s.outputs); return f"{n} displays connected" if n>1 else "1 display connected"

    def draw(self, s):
        if not s.available: self.note(s.message); return
        outs=s.outputs; on=[o for o in outs if o.enabled]; where=display.placements(outs); ref=display.reference(outs)
        if len(outs)>1 and on: self.add(self.preview(outs))
        for i,o in enumerate(outs,1):
            self.section(f"{i} · {o.title}".upper()+(f"  ({o.name})" if o.label else ""))
            if len(outs)>1:
                self.row("Use this display",_on_off(o.enabled),lambda o=o:self.switch(o),ident=f"{o.name}:on")
            if not o.enabled: continue
            mode=o.mode()
            self.row("Resolution",(display.mode_text(mode) if mode else f"{o.width} × {o.height}")+(" (recommended)" if mode and mode.preferred else ""),
                     (lambda o=o:self.choose_mode(o)) if len(o.modes)>1 else None,ident=f"{o.name}:mode")
            rates=mode.rates if mode else []
            if o.rate or rates:
                self.row("Refresh rate",display.rate_text(o.rate) if o.rate else "—",(lambda o=o:self.choose_rate(o)) if len(rates)>1 else None,ident=f"{o.name}:rate")
            if len(on)>1:
                if o is ref:
                    other=next((x for x in on if where.get(x.name,("",""))[1]==o.name),None)
                    value=display.RELATION_TEXT[display.relation(o,other)].format(other.title) if other else ""
                else:
                    rel,anchor=where[o.name]; value=display.RELATION_TEXT[rel].format(next(x.title for x in outs if x.name==anchor))
                self.row("Position",value,lambda o=o:self.choose_place(o),ident=f"{o.name}:place")
                if s.can_set_primary:
                    self.row("Primary display","Yes" if o.primary else "No",(lambda o=o:self.change(o,False,primary=True)) if not o.primary else None,
                             detail="" if o.primary else "Make this the primary display",ident=f"{o.name}:primary")
        notes=[f"A new resolution, refresh rate or display switched on or off goes back after {self.KEEP_SECONDS} seconds unless you keep it, "
               "in case a display cannot show it."]
        if len(on)>1 and s.can_set_primary: notes.append("The primary display holds the status bar's tray and is where the session starts.")
        notes.append("What you keep is used again at the next log-in, as long as the same displays are connected.")
        self.note(" ".join(notes))

    def preview(self, outs):
        """The displays that are on, drawn where they are, each with the number of its section."""
        on=[(i,o) for i,o in enumerate(outs,1) if o.enabled]
        minx=min(o.x for _i,o in on); miny=min(o.y for _i,o in on)
        maxx=max(o.x+o.size[0] for _i,o in on); maxy=max(o.y+o.size[1] for _i,o in on)
        k=min(S(560)/max(1,maxx-minx),S(180)/max(1,maxy-miny))
        fixed=Gtk.Fixed(); fixed.set_halign(Gtk.Align.CENTER); fixed.set_margin_top(S(8)); fixed.set_margin_bottom(S(8))
        fixed.set_size_request(round((maxx-minx)*k)+S(16),round((maxy-miny)*k)+S(16)); seen={}
        for i,o in on:
            shift=seen.get((o.x,o.y),0); seen[(o.x,o.y)]=shift+1   # mirrored displays sit on each other: offset a little
            w,h=o.size; box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0); box.add_css_class("display-box")
            if o.primary: box.add_css_class("primary")
            box.set_size_request(max(S(24),round(w*k)),max(S(24),round(h*k))); box.set_overflow(Gtk.Overflow.HIDDEN)
            number=Gtk.Label(label=str(i)); number.add_css_class("display-number"); number.set_vexpand(True); box.append(number)
            name=Gtk.Label(label=o.title); name.add_css_class("display-name"); name.set_ellipsize(Pango.EllipsizeMode.END); name.set_margin_bottom(S(4))
            name.set_margin_start(S(4)); name.set_margin_end(S(4)); box.append(name)
            fixed.put(box,round((o.x-minx)*k)+shift*S(8),round((o.y-miny)*k)+shift*S(8))
        return fixed

    # ---------------------------------------------------------- choosing
    def choose_mode(self, o):
        mode=o.mode()
        self.win.choose_option(f"Resolution · {o.title}",[(m.key,display.mode_text(m)+(" (recommended)" if m.preferred else "")) for m in o.modes],
                               mode.key if mode else None,lambda key:self.change(o,True,mode=key))
    def choose_rate(self, o):
        mode=o.mode()
        self.win.choose_option(f"Refresh rate · {o.title}",[(r,display.rate_text(r)) for r in mode.rates],o.rate,lambda r:self.change(o,True,rate=r))
    def choose_place(self, o):
        where=display.placements(self.state.outputs).get(o.name)
        def picked(key): rel,anchor=key.split(":",1); self.change(o,False,place=(rel,anchor))
        self.win.choose_option(f"Position · {o.title}",display.choices(self.state.outputs,o),f"{where[0]}:{where[1]}" if where else None,picked)
    def switch(self, o):
        if o.enabled and sum(x.enabled for x in self.state.outputs)==1:
            self.win.notice("Displays","This is the only display that is on, so it stays on."); return
        self.change(o,True,enabled=not o.enabled)

    # ---------------------------------------------------------- changing
    def change(self, o, risky, **changes):
        """Apply a change to one display now. A risky one waits to be kept, else goes back; the rest are kept at once."""
        s=self.state; old=s.outputs; new=display.edited(old,o.name,**changes)
        self.set_status("Changing the displays…"); self.busy=True
        def done(problem):
            self.busy=False; self.set_status("")
            if problem: self.win.notice("Displays",problem); self.refresh(quiet=True)
            elif risky: GLib.timeout_add(600,lambda:(self.ask_keep(s,old,new),GLib.SOURCE_REMOVE)[1])   # let the screen settle first
            else: self.keep(s,new)
        in_background(lambda:display.apply(s,new),done,lambda exc:done(str(exc)))
    def ask_keep(self, s, old, new):
        def message(n): return f"Keep these display settings? They go back in {n} second{'s' if n!=1 else ''}."
        def undo():
            self.set_status("Going back…"); self.busy=True
            def done(problem):
                self.busy=False; self.set_status("")
                if problem: self.win.notice("Displays",f"Could not go back to the earlier settings: {problem}")
                self.refresh(quiet=True)
            in_background(lambda:display.apply(s,old),done,lambda exc:done(str(exc)))
        self.win.countdown("Displays",message,self.KEEP_SECONDS,"Keep",lambda:self.keep(s,new),"Go back",undo)
    def keep(self, s, outputs):
        try: display.save(s,outputs)
        except OSError as exc: self.win.notice("Displays",f"The change is in use, but could not be saved for the next log-in: {exc}")
        self.refresh(quiet=True)

# ====================================================================== Bluetooth
class BluetoothPage(Page):
    key="bluetooth"; title="Bluetooth"; icon="bluetooth-active-symbolic"; fallback="ᛒ"; poll=4
    scanning=False
    def read(self): return bluetooth.read_state()
    def summary(self):
        s=self.state
        if not s or not s.available: return ""
        return ("Searching for devices…" if self.scanning else f"Adapter {s.controller}")
    def draw(self, s):
        if not s.available: self.note(s.message); return
        self.row("Bluetooth",_on_off(s.powered),lambda:self.act(lambda:bluetooth.set_powered(not s.powered),
                 "Switching Bluetooth "+("off…" if s.powered else "on…"),"Bluetooth"),ident="power")
        if s.blocked: self.note("Bluetooth is switched off by rfkill (airplane mode); turning it on here lifts that.")
        if not s.powered: self.note("Turn Bluetooth on to connect headphones, speakers, game controllers and remotes."); return
        self.row("Search for devices","Searching…" if self.scanning else "",None if self.scanning else self.scan,
                 detail="Put the device in pairing mode first.",icon="edit-find-symbolic",fallback="⌕",ident="scan")
        self.section("MY DEVICES")
        if not s.paired: self.note("No device is paired yet. Search for devices, then choose one to pair it.")
        for d in s.paired: self.device_row(d)
        self.section("OTHER DEVICES")
        named=[d for d in s.nearby if d.name and d.name.replace("-",":").upper()!=d.address]
        if not named: self.note("None found yet. Choose Search for devices." if not self.scanning else "Looking…")
        for d in named: self.device_row(d)
        if len(named)<len(s.nearby): self.note(f"{len(s.nearby)-len(named)} unnamed devices nearby are not listed.")

    def device_row(self, d):
        icon,fallback,kind=d.kind
        detail=" · ".join(x for x in (kind,f"Battery {d.battery} %" if d.battery is not None else "",d.address) if x)
        if not d.paired:
            self.row(d.name,"Pair",lambda d=d:self.act(lambda:bluetooth.pair(d.address),f"Pairing with {d.name}…",f"Pair {d.name}"),
                     detail=detail,icon=icon,fallback=fallback,ident=f"bt:{d.address}"); return
        forget=self.button("user-trash-symbolic","✕",f"Forget {d.name}",lambda d=d:self.win.confirm(f"Forget {d.name}?",
                           f"{d.name} will be disconnected and unpaired. To use it again, pair it again.","Forget",
                           lambda:self.act(lambda:bluetooth.forget(d.address),f"Forgetting {d.name}…","Bluetooth")),danger=True)
        if d.connected:
            go=lambda d=d:self.act(lambda:bluetooth.disconnect(d.address),f"Disconnecting {d.name}…","Bluetooth")
        else:
            go=lambda d=d:self.act(lambda:bluetooth.connect(d.address),f"Connecting to {d.name}…",f"Connect {d.name}")
        self.row(d.name,"Connected" if d.connected else "Not connected",go,detail=detail,icon=icon,fallback=fallback,
                 ident=f"bt:{d.address}",extras=[forget],value_css="state-on" if d.connected else "setting-value")

    def scan(self):
        self.scanning=True; self.redraw(); self.set_status("Searching for devices…")
        def done(_result):
            self.scanning=False; self.set_status(""); self.busy=False; self.refresh(quiet=True)
        in_background(lambda:bluetooth.scan(),done,lambda _e:done(None))

# ====================================================================== Software updates
class UpdatesPage(Page):
    key="updates"; title="Software updates"; icon="software-update-available-symbolic"; fallback="⇩"
    MAX_ROWS=300
    def __init__(self, win):
        super().__init__(win); self.running=None; self.log=None; self.fetched=None
    def read(self):
        state=updates.read_state(); state.reboot=updates.reboot_needed()
        if self.fetched and (state.checked or 0)<self.fetched: state.checked=self.fetched   # unchanged lists keep their old date
        return state
    def summary(self):
        s=self.state
        if not s or not s.available or s.manager is None: return ""
        age=updates.age_text(s.checked)
        return s.manager.label+(f" · package lists from {age}" if age else "")
    def draw(self, s):
        if not s.available: self.note(s.message); return
        if self.running:
            self.row(self.running,"Working…",None,icon="emblem-synchronizing-symbolic",fallback="⟳",ident="running")
            self.note("Leave this running until it finishes. The Control Panel can be closed; the update carries on.")
            self.add(self.console()); return
        self.row("Check for updates",f"{s.total} available" if s.total else "Up to date",self.refresh,ident="check",
                 icon="view-refresh-symbolic",fallback="⟳")
        m=s.manager
        if m is not None and m.refresh_argv:
            self.row("Download the latest package lists","",lambda:self.run_steps("Downloading package lists",[(list(m.refresh_argv),True)],fetch=True),
                     detail="Asks for your password. Then check again.",icon="folder-download-symbolic",fallback="⇩",ident="lists")
        if s.total:
            self.row(f"Install {s.total} update{'s' if s.total!=1 else ''}","",self.confirm_install,ident="install",
                     detail="Installs everything listed below." + (" Asks for your password." if s.updates else ""),
                     icon="software-update-available-symbolic",fallback="⇩")
        if getattr(s,"reboot",False):
            self.row("Restart to finish updating","",self.confirm_reboot,detail="Some updates are only used after a restart.",
                     icon="system-reboot-symbolic",fallback="↻",ident="reboot")
        for label,problem in s.problems: self.note(f"{label}: {problem}","error")
        if self.log is not None and self.log.get_buffer().get_char_count():
            self.section("LAST RUN"); self.add(self.console())
        for title,items in ((f"{m.label.upper()} PACKAGES" if m else "PACKAGES",s.updates),("FLATPAK APPS",s.flatpak)):
            if not items: continue
            self.section(f"{title} ({len(items)})")
            for u in items[:self.MAX_ROWS]:
                self.row(u.name,f"{u.old} → {u.new}" if u.old else u.new,lambda u=u:self.details(u),detail=u.source,ident=f"pkg:{title}:{u.name}")
            if len(items)>self.MAX_ROWS: self.note(f"… and {len(items)-self.MAX_ROWS} more.")

    def console(self):
        if self.log is None:
            self.log=Gtk.TextView(); self.log.set_editable(False); self.log.set_cursor_visible(False); self.log.set_focusable(False)
            self.log.add_css_class("console"); self.log.set_wrap_mode(Gtk.WrapMode.WORD_CHAR); self.log.set_monospace(True)
            self.log_scroll=Gtk.ScrolledWindow(); self.log_scroll.set_child(self.log); self.log_scroll.set_min_content_height(S(280))
            self.log_scroll.add_css_class("console-frame"); self.log_scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.AUTOMATIC)
        if self.log_scroll.get_parent() is not None: self.log_scroll.get_parent().remove(self.log_scroll)
        return self.log_scroll
    def _append(self, line):
        buf=self.log.get_buffer(); buf.insert(buf.get_end_iter(),line+"\n")
        if buf.get_line_count()>2000: buf.delete(buf.get_start_iter(),buf.get_iter_at_line(buf.get_line_count()-2000)[1])
        GLib.idle_add(lambda:(self.log_scroll.get_vadjustment().set_value(self.log_scroll.get_vadjustment().get_upper()),GLib.SOURCE_REMOVE)[1])

    def details(self, u):
        lines=[f"Version {u.new}"]+([f"Installed now: {u.old}"] if u.old else [])+([f"From: {u.source}"] if u.source else [])
        self.win.notice(u.name,"\n".join(lines))

    def confirm_install(self):
        s=self.state; parts=[]
        if s.updates: parts.append(f"{len(s.updates)} package{'s' if len(s.updates)!=1 else ''} from {s.manager.label}")
        if s.flatpak: parts.append(f"{len(s.flatpak)} Flatpak app{'s' if len(s.flatpak)!=1 else ''}")
        steps=[]
        if s.updates: steps.append((list(s.manager.install_argv),True))
        if s.flatpak: steps.append((list(updates.FLATPAK.install_argv),False))
        self.win.confirm("Install updates?",f"Install {' and '.join(parts)} now? Apps being updated may need to be restarted afterwards.",
                         "Install",lambda:self.run_steps("Installing updates",steps),danger=False)

    def run_steps(self, label, steps, fetch=False):
        """Run each (argv, as root) in turn, showing their output; stop at the first that fails."""
        self.running=label; self.console(); self.log.get_buffer().set_text(""); self.redraw(); self.set_status(label+"…")
        self.win._focus_first(self.groups)
        def finish(problem=""):
            self.running=None; self.set_status(""); self.redraw()
            if problem: self.win.notice(label,problem)
            self.refresh()
        def next_step(i):
            if i>=len(steps):
                if fetch: self.fetched=time.time()
                finish(); return
            argv,root=steps[i]; self._append("$ "+" ".join(argv))
            def done(code,tail):
                if code!=0: finish(tail.strip().splitlines()[-1] if tail.strip() else f"It stopped with exit status {code}."); return
                next_step(i+1)
            if root: self.win.run_as_root(argv,label,self._append,done)
            else: StreamedRun(argv,self._append,done)
        next_step(0)

    def confirm_reboot(self):
        command=command_for("reboot")
        if not command: self.win.notice("Restart","Nothing on this system can restart it from here."); return
        def go():
            if privilege.needs_root(command): self.win.run_as_root(command,"Restart",lambda _l:None,lambda code,tail:code and self.win.notice("Restart",tail))
            else:
                def done(code,tail):
                    if code and privilege.polkit_refused(tail): self.win.run_as_root(command,"Restart",lambda _l:None,lambda c,t:c and self.win.notice("Restart",t))
                    elif code: self.win.notice("Restart",tail)
                StreamedRun(command,lambda _l:None,done)
        self.win.confirm("Restart now?","Restart the computer now? Unsaved work in open applications may be lost.","Restart",go)

# ====================================================================== System information
class SystemPage(Page):
    key="system"; title="System information"; icon="computer-symbolic"; fallback="🖥"
    def read(self): return sysinfo.read_sections()
    def summary(self): return ""
    def draw(self, sections):
        displays=self.displays()
        if displays: sections=sections[:2]+[("DISPLAYS",displays)]+sections[2:]
        for title,rows in sections:
            self.section(title)
            for i,(label,value) in enumerate(rows): self.row(label,value,None,ident=f"{title}:{label}:{i}")
    def displays(self):
        display=Gdk.Display.get_default(); monitors=display.get_monitors() if display else None; rows=[]
        for i in range(monitors.get_n_items() if monitors is not None else 0):
            m=monitors.get_item(i); g=m.get_geometry(); f=max(1,m.get_scale_factor()); hz=m.get_refresh_rate()/1000 if m.get_refresh_rate() else 0
            name=" ".join(x for x in ((m.get_manufacturer() or ""),(m.get_model() or "")) if x).strip() or (m.get_connector() or f"Display {i+1}")
            rows.append((name,f"{g.width*f} × {g.height*f}"+(f" at {hz:.0f} Hz" if hz else "")))
        return rows

# ====================================================================== Terminal
class TerminalPage(Page):
    key="terminal"; title="Terminal"; icon="utilities-terminal-symbolic"; fallback="▮"; refreshable=False
    def __init__(self, win):
        super().__init__(win); self.terminal=None; self.child=None; self.process=None
    def summary(self): return os.environ.get("SHELL","/bin/sh") if Vte is not None else "Command console"

    def content(self):
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(6)); box.set_margin_start(S(24)); box.set_margin_end(S(24)); box.set_margin_bottom(S(16))
        bar=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(4)); box.append(bar)
        if Vte is not None:
            restart=Gtk.Button(label="New session"); restart.connect("clicked",lambda *_:self.start(restart=True))
            copy=Gtk.Button(label="Copy"); copy.connect("clicked",lambda *_:self.terminal.copy_clipboard_format(Vte.Format.TEXT))
            paste=Gtk.Button(label="Paste"); paste.connect("clicked",lambda *_:self.terminal.paste_clipboard())
            for b in (restart,copy,paste): bar.append(b)
            hint=muted_label("Every key goes to the terminal. Back (or Shift+Esc) returns to the tabs. Ctrl+Shift+C and Ctrl+Shift+V copy and paste.")
            hint.set_hexpand(True); hint.set_margin_start(S(12)); bar.append(hint)
            self.terminal=Vte.Terminal(); self.terminal.set_vexpand(True); self.terminal.set_hexpand(True)
            self.terminal.set_font_scale(max(1.0,self.win.app.scale)); self.terminal.set_scrollback_lines(5000)
            fg=Gdk.RGBA(); fg.parse("#d0d0d0"); bg=Gdk.RGBA(); bg.parse("#0c0c0c"); self.terminal.set_colors(fg,bg,None)
            self.terminal.connect("child-exited",self._exited)
            keys=Gtk.EventControllerKey(); keys.connect("key-pressed",self._terminal_key); self.terminal.add_controller(keys)
            frame=Gtk.Box(); frame.add_css_class("console-frame"); frame.append(self.terminal); box.append(frame)
            self.groups=[NavGroup([restart,copy,paste]),NavGroup([self.terminal])]
        else:
            self.entry=Gtk.Entry(); self.entry.set_hexpand(True); self.entry.set_placeholder_text("Type a command, then Enter")
            self.entry.connect("activate",lambda *_:self.run_command(self.entry.get_text()))
            run=Gtk.Button(label="Run"); run.add_css_class("active"); run.connect("clicked",lambda *_:self.run_command(self.entry.get_text()))
            stop=Gtk.Button(label="Stop"); stop.connect("clicked",lambda *_:self.process and self.process.stop())
            keyboard=Gtk.Button(); keyboard.set_child(glyph("input-keyboard-symbolic","⌨")); keyboard.add_css_class("square"); keyboard.set_tooltip_text("Type the command on the on-screen keyboard")
            keyboard.connect("clicked",lambda *_:self.win.ask_text("Command","Runs with sh -c in your home folder.",self.run_command,self.entry.get_text(),ok_label="Run"))
            for w in (self.entry,run,stop,keyboard): bar.append(w)
            box.append(muted_label("A full terminal needs VTE for GTK 4 (gir1.2-vte-3.91, vte4 or vte291-gtk4). Until then commands run here one at a time, without input."))
            self.output=Gtk.TextView(); self.output.set_editable(False); self.output.set_cursor_visible(False); self.output.set_focusable(False)
            self.output.add_css_class("console"); self.output.set_monospace(True); self.output.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            scroll=Gtk.ScrolledWindow(); scroll.set_vexpand(True); scroll.set_child(self.output); scroll.add_css_class("console-frame"); self.output_scroll=scroll; box.append(scroll)
            self.groups=[NavGroup([self.entry,run,stop,keyboard])]
        return box

    def redraw(self): pass   # nothing here is drawn from a state
    def shown(self):
        if Vte is not None and self.child is None: self.start()
    def captures_keys(self, focused):
        return self.terminal is not None and focused is not None and (focused is self.terminal or focused.is_ancestor(self.terminal))

    def start(self, restart=False):
        if restart and self.child:
            try: os.kill(self.child,9)
            except OSError: pass
        self.child=None; self.terminal.reset(True,True)
        shell=os.environ.get("SHELL") or "/bin/sh"
        def spawned(_term,pid,error,*_):
            if error is not None or pid<0: self.terminal.feed(f"Could not start {shell}: {error.message if error else ''}\r\n".encode()); return
            self.child=pid
        self.terminal.spawn_async(Vte.PtyFlags.DEFAULT,os.path.expanduser("~"),[shell],None,GLib.SpawnFlags.DEFAULT,None,None,-1,None,spawned)
        if restart: self.terminal.grab_focus()
    def _exited(self, *_):
        self.child=None; self.terminal.feed(b"\r\n[The shell has ended. Choose New session to start another.]\r\n")
    def _terminal_key(self, _controller, keyval, _keycode, state):
        ctrl_shift=Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.SHIFT_MASK
        if state & ctrl_shift==ctrl_shift and keyval in (Gdk.KEY_C,Gdk.KEY_c): self.terminal.copy_clipboard_format(Vte.Format.TEXT); return True
        if state & ctrl_shift==ctrl_shift and keyval in (Gdk.KEY_V,Gdk.KEY_v): self.terminal.paste_clipboard(); return True
        return False

    def run_command(self, command):
        command=(command or "").strip()
        if not command: return
        if self.process is not None and self.process.proc is not None and self.process.proc.poll() is None:
            self.win.notice("Terminal","A command is still running. Stop it first."); return
        self.entry.set_text(""); self._out(f"$ {command}")
        def done(code,_tail):
            self.process=None; self._out(f"[exit status {code}]\n" if code else "")
        self.process=StreamedRun(["sh","-c",f"cd ~ && {command}"],self._out,done,env=None)
    def _out(self, line):
        if not line: return
        buf=self.output.get_buffer(); buf.insert(buf.get_end_iter(),line+"\n")
        GLib.idle_add(lambda:(self.output_scroll.get_vadjustment().set_value(self.output_scroll.get_vadjustment().get_upper()),GLib.SOURCE_REMOVE)[1])

# ====================================================================== Network
class NetworkPage(Page):
    key="network"; title="Network"; icon="network-wired-symbolic"; fallback="⇄"; poll=6
    scanning=False
    def read(self): return network.read_state(scan=self.scanning)
    def summary(self):
        s=self.state
        if not s: return ""
        return "NetworkManager" if s.managed else "Shown only (no NetworkManager)"
    def draw(self, s):
        if not s.managed: self.note(s.message)
        self.section("ETHERNET")
        wired=s.of_kind("ethernet")
        if not wired: self.note("No Ethernet port was found.")
        for i in wired: self.ethernet_row(i,s.managed)
        self.section("WI-FI")
        wireless=s.of_kind("wifi")
        if not wireless: self.note("No Wi-Fi adapter was found."); return
        if not s.managed:
            for i in wireless: self.ethernet_row(i,False)
            return
        self.row("Wi-Fi",_on_off(s.wifi_enabled),lambda:self.act(lambda:network.set_wifi(not s.wifi_enabled),
                 "Switching Wi-Fi "+("off…" if s.wifi_enabled else "on…"),"Wi-Fi"),icon="network-wireless-symbolic",fallback="📶",ident="wifi")
        if not s.wifi_enabled: return
        self.row("Search for networks","Searching…" if self.scanning else "",None if self.scanning else self.scan,icon="edit-find-symbolic",fallback="⌕",ident="scan")
        if not s.networks: self.note("No networks found yet." if not self.scanning else "Looking…")
        device=wireless[0]
        for n in s.networks: self.wifi_row(n,device)

    @staticmethod
    def _details(i):
        return " · ".join(x for x in (", ".join(i.addresses),f"Gateway {i.gateway}" if i.gateway else "",
                                       f"DNS {', '.join(i.dns)}" if i.dns else "",f"MAC {i.mac}" if i.mac else "") if x)
    @staticmethod
    def _state_text(i):
        if i.connected: return "Connected"
        return {"unavailable":"No cable","disconnected":"Not connected","unmanaged":"Not managed"}.get(i.state.split(" ")[0],i.state.capitalize() or "Unknown")

    def ethernet_row(self, i, managed):
        go=None; extras=[]
        if managed and i.state not in ("unavailable","unmanaged"):
            if i.connected:
                go=lambda i=i:self.win.confirm(f"Disconnect {i.device}?",f"Disconnect {i.connection or i.device}? Anything using the network will lose it until you connect again.",
                                               "Disconnect",lambda:self.act(lambda:network.disconnect_device(i.device),f"Disconnecting {i.device}…","Ethernet"))
            else: go=lambda i=i:self.act(lambda:network.connect_device(i.device),f"Connecting {i.device}…","Ethernet")
        if managed and i.connection_uuid:
            extras.append(self.button("emblem-system-symbolic","⚙",f"IP settings of {i.connection or i.device}",lambda i=i:self.ip_settings(i.connection_uuid,i.connection or i.device)))
        label=("Ethernet" if i.kind=="ethernet" else "Wi-Fi")+f" ({i.device})"
        self.row(label,self._state_text(i),go,detail=self._details(i),icon="network-wired-symbolic" if i.kind=="ethernet" else "network-wireless-symbolic",
                 fallback="⇄",ident=f"if:{i.device}",extras=extras,value_css="state-on" if i.connected else "setting-value")

    def wifi_row(self, n, device):
        detail=f"{network.signal_bars(n.signal)}  {n.signal} %"+(f" · {n.security}" if n.secured else " · Open")
        if n.in_use and device.addresses: detail+=" · "+self._details(device)
        extras=[]
        if n.in_use and device.connection_uuid:
            extras.append(self.button("emblem-system-symbolic","⚙",f"IP settings of {n.ssid}",lambda:self.ip_settings(device.connection_uuid,n.ssid)))
        if n.saved_uuid:
            extras.append(self.button("user-trash-symbolic","✕",f"Forget {n.ssid}",lambda n=n:self.win.confirm(f"Forget {n.ssid}?",
                          f"The saved password and settings for {n.ssid} are removed"+(", and this computer leaves it." if n.in_use else "."),
                          "Forget",lambda:self.act(lambda:network.forget(n.saved_uuid),f"Forgetting {n.ssid}…","Wi-Fi")),danger=True))
        if n.in_use:
            go=lambda n=n:self.win.confirm(f"Disconnect from {n.ssid}?","Anything using the network will lose it until you connect again.","Disconnect",
                                          lambda:self.act(lambda:network.disconnect_device(device.device),f"Disconnecting from {n.ssid}…","Wi-Fi"))
        elif n.saved_uuid: go=lambda n=n:self.act(lambda:network.activate(n.saved_uuid),f"Connecting to {n.ssid}…",f"Connect to {n.ssid}")
        elif n.secured: go=lambda n=n:self.ask_password(n)
        else: go=lambda n=n:self.act(lambda:network.join_wifi(n.ssid),f"Connecting to {n.ssid}…",f"Connect to {n.ssid}")
        locked=n.secured
        self.row(n.ssid,"Connected" if n.in_use else "Saved" if n.saved_uuid else "",go,detail=detail,
                 icon="network-wireless-encrypted-symbolic" if locked else "network-wireless-symbolic",fallback="🔒" if locked else "📶",
                 ident=f"wifi:{n.ssid}",extras=extras,value_css="state-on" if n.in_use else "setting-value")

    def ask_password(self, n, error=""):
        def join(password):
            if not password: return
            def work():
                problem=network.join_wifi(n.ssid,password)
                if problem!="The password was not accepted.": return problem
                GLib.idle_add(lambda:(self.ask_password(n,"The password was not accepted. Try again."),GLib.SOURCE_REMOVE)[1]); return ""
            self.act(work,f"Connecting to {n.ssid}…",f"Connect to {n.ssid}")
        self.win.ask_text(f"Password for {n.ssid}",f"{n.security} network. NetworkManager saves the password for next time.",join,secret=True,ok_label="Connect",error=error)

    def scan(self):
        self.scanning=True; self.redraw(); self.set_status("Searching for networks…")
        def done(state):
            self.scanning=False; self.busy=False; self.set_status("")
            if state is not None: self.state=state
            self.redraw()
        self.busy=True; in_background(lambda:network.read_state(scan=True),done,lambda _e:done(None))

    def ip_settings(self, uuid, name):
        self.set_status("Reading IP settings…")
        in_background(lambda:network.read_ipv4(uuid),lambda s:(self.set_status(""),self.ip_form(uuid,name,s)))
    def ip_form(self, uuid, name, s, error=""):
        again=lambda error="":self.ip_form(uuid,name,s,error)
        def edit(field,title,message):
            def set_value(text): setattr(s,field,text.strip()); again()
            self.win.ask_text(title,message,set_value,getattr(s,field),back=lambda:again())
        def flip(): s.method="auto" if s.method=="manual" else "manual"; again()
        rows=[("Addresses","Automatic (DHCP)" if s.automatic else "Manual",flip)]
        if not s.automatic:
            rows+=[("IP address",s.address,lambda:edit("address","IP address","With its prefix, for example 192.168.1.20/24 (without one, /24 is used).")),
                   ("Gateway",s.gateway,lambda:edit("gateway","Gateway","The router's address, for example 192.168.1.1. Can be left empty.")),
                   ("DNS servers",s.dns,lambda:edit("dns","DNS servers","One or more, separated by commas, for example 1.1.1.1, 9.9.9.9."))]
        def save():
            problem,_args=network.validate_ipv4(s)
            if problem: again(problem); return
            self.win.close_modal()
            self.act(lambda:network.apply_ipv4(uuid,s),f"Applying the IP settings of {name}…","IP settings")
        self.win.form(f"IP settings · {name}",rows,"Save",save,
                      "Automatic asks the router for an address. Saving reconnects, so the connection drops for a moment.",error)

PAGES=(SoundPage,DisplaysPage,BluetoothPage,UpdatesPage,SystemPage,TerminalPage,NetworkPage)
