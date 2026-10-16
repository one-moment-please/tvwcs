"""TVWCS's login screen (greeter): pick who is logging in, type the password on a keyboard or with the remote on the
on-screen keyboard (the full one, or a number pad for a password of digits), choose the session, and log in. Restart,
shut down and sleep are at the bottom. greetd runs it full screen in cage; see loginscreen.py for how it is set up.

`python3 -m tvwcs.ui_greeter --demo` shows it in a window without greetd: any password but "wrong" logs in."""
from __future__ import annotations
import datetime, os, socket, subprocess, sys, threading
from pathlib import Path
import gi
gi.require_version("Gtk","4.0")
gi.require_version("Gdk","4.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from tvwcs import greeter, loginscreen
from tvwcs.model import effective_scale
from tvwcs.theme import render_css
from tvwcs.widgets import METRO_COLORS, S, clear_box, glyph, screen_height, set_scale, usable

APP_ID="com.tvwcs.Greeter"
GREETER_CSS="""
.greeter-title { font-size: 64px; font-weight: 200; }
.greeter-host { color: @MUTED@; font-size: 18px; }
.greeter-user { font-size: 40px; font-weight: 200; }
.greeter-tile { font-size: 56px; font-weight: 300; color: #ffffff; }
button.user-button { padding: 10px; background: transparent; }
button.user-button:focus, button.user-button:focus-visible { background: @ACCENT@; }
.user-name { font-size: 20px; }
button.key { min-height: 52px; min-width: 44px; padding: 0 6px; font-size: 20px; }
button.key.letter { min-height: 68px; min-width: 68px; padding: 0; font-size: 40px; }
button.key.pad { min-height: 76px; min-width: 76px; padding: 0; font-size: 40px; }
button.key.wide { font-size: 16px; min-height: 56px; }
entry.password-field { font-size: 26px; min-height: 56px; }
.signing-in { color: @MUTED@; }
.greeter-status { font-size: 18px; }
"""
KEYS={"lower":("1234567890","qwertyuiop","asdfghjkl'","zxcvbnm,.-"),
      "upper":("1234567890","QWERTYUIOP","ASDFGHJKL\"","ZXCVBNM;:_"),
      "symbols":("!@#$%^&*()","`~-_=+[]{}","\\|;:'\",.<>","/?€£¥§°·×÷")}

class DemoGreetd:
    """--demo: logs in with any password but "wrong", and only says so."""
    def create_session(self, username): return {"type":"auth_message","auth_message_type":"secret","auth_message":"Password: "}
    def answer(self, response=None):
        return {"type":"error","error_type":"auth_error","description":"wrong"} if response=="wrong" else {"type":"success"}
    def start_session(self, cmd, env=()): print("Would start:",cmd,env); return {"type":"success"}
    def cancel(self): return {"type":"success"}

def tv_mark(size):
    """TVWCS's icon (TV, underlined with a thin oval), size pixels square, or None when its file is missing."""
    here=Path(__file__).resolve().parent
    for f in (Path(loginscreen.GREETER_LIB)/"tvwcs.svg",here.parent/"tvwcs.svg",here.parent.parent/"data"/"tvwcs.svg"):
        if f.is_file():
            pic=Gtk.Picture.new_for_filename(str(f)); pic.set_size_request(S(size),S(size)); pic.set_can_shrink(True)
            pic.set_content_fit(Gtk.ContentFit.CONTAIN); pic.set_valign(Gtk.Align.CENTER); return pic
    return None

class GreeterWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app,title="Log in")
        self.app=app; self.add_css_class("tvwcs-window")
        self.people=greeter.users() or ([(os.environ.get("USER","demo"),"Demo user")] if app.demo else [])
        self.sessions=loginscreen.sessions(); self.memory=greeter.Memory(app.state_dir)
        self.user=None; self.session=""; self.digits=False; self.layer="lower"; self.keys=[]; self.typed=False
        self.rows=[]; self.modal_rows=None; self.modal_back=None; self.busy=False
        overlay=Gtk.Overlay(); self.set_child(overlay)
        root=Gtk.Box(orientation=Gtk.Orientation.VERTICAL); root.add_css_class("tvwcs-root"); overlay.set_child(root)
        top=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL); top.set_margin_top(S(40)); top.set_margin_start(S(60)); top.set_margin_end(S(60))
        host=Gtk.Label(label=socket.gethostname().split(".")[0]); host.add_css_class("greeter-host"); host.set_xalign(0); host.set_hexpand(True); host.set_valign(Gtk.Align.START)
        mark=tv_mark(44)
        if mark: mark.set_margin_end(S(16)); top.append(mark); host.set_valign(Gtk.Align.CENTER)
        top.append(host)
        clock=Gtk.Box(orientation=Gtk.Orientation.VERTICAL); self.time=Gtk.Label(); self.time.add_css_class("clock-time"); self.time.set_xalign(1)
        self.date=Gtk.Label(); self.date.add_css_class("clock-date"); self.date.set_xalign(1); clock.append(self.time); clock.append(self.date); top.append(clock)
        root.append(top)
        self.body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL); self.body.set_vexpand(True); self.body.set_valign(Gtk.Align.CENTER)
        self.body.set_margin_start(S(110)); self.body.set_margin_end(S(110)); root.append(self.body)
        bottom=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(6)); bottom.set_halign(Gtk.Align.END); bottom.set_margin_end(S(60)); bottom.set_margin_bottom(S(40))
        self.power=[]
        for label,icon,fallback,verb in (("Sleep","weather-clear-night-symbolic","☾","suspend"),("Restart","system-reboot-symbolic","↻","reboot"),
                                          ("Shut down","system-shutdown-symbolic","⏻","poweroff")):
            b=Gtk.Button(); line=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(8)); line.append(glyph(icon,fallback)); line.append(Gtk.Label(label=label))
            b.set_child(line); b.connect("clicked",lambda _b,l=label,v=verb:self.ask_power(l,v)); bottom.append(b); self.power.append(b)
        root.append(bottom)
        self.scrim=Gtk.Box(); self.scrim.add_css_class("modal-scrim"); self.scrim.set_visible(False); overlay.add_overlay(self.scrim)
        self.card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4)); self.card.add_css_class("modal-card"); self.card.set_halign(Gtk.Align.CENTER)
        self.card.set_valign(Gtk.Align.CENTER); self.card.set_size_request(S(560),-1); self.scrim.append(self.card); self.card.set_hexpand(True)
        # cage puts the pointer in the middle of the screen: hidden until the mouse is really moved
        self.set_cursor_from_name("none"); self._pointer=None; motion=Gtk.EventControllerMotion(); motion.connect("motion",self.pointer_moved); self.add_controller(motion)
        keys=Gtk.EventControllerKey(); keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE); keys.connect("key-pressed",self.key_pressed); self.add_controller(keys)
        self.tick(); GLib.timeout_add_seconds(5,self.tick)
        if not self.people: self.show_message("Nobody can log in","There are no user accounts on this computer that can log in."); return
        last=self.memory.last_user if any(u==self.memory.last_user for u,_n in self.people) else self.people[0][0]
        if len(self.people)==1: self.show_password(last)
        else: self.show_users(last)

    def pointer_moved(self, _controller, x, y):
        if self._pointer is None: self._pointer=(x,y); return
        if abs(x-self._pointer[0])+abs(y-self._pointer[1])>8: self.set_cursor(None)
    def tick(self):
        now=datetime.datetime.now()
        self.time.set_text(now.strftime("%H:%M") if self.app.clock_24h else now.strftime("%I:%M %p").lstrip("0"))
        self.date.set_text(now.strftime("%A, %B %d").replace(" 0"," ")); return GLib.SOURCE_CONTINUE

    # ---------------------------------------------------------- who
    def show_users(self, selected=None):
        self.user=None; clear_box(self.body); self.rows=[]
        t=Gtk.Label(label="Who is it?"); t.add_css_class("greeter-title"); t.set_xalign(0); t.set_margin_bottom(S(30)); self.body.append(t)
        flow=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(16)); self.body.append(flow); row=[]; focus=None
        for login,full in self.people:
            b=Gtk.Button(); b.add_css_class("user-button"); box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(10))
            box.append(self.tile(full,150)); n=Gtk.Label(label=full); n.add_css_class("user-name"); n.set_max_width_chars(14); n.set_ellipsize(3); box.append(n)
            b.set_child(box); b.connect("clicked",lambda _b,u=login:self.show_password(u)); flow.append(b); row.append(b)
            if login==selected: focus=b
        self.rows=[row,self.power]; self.focus(focus or row[0])

    def tile(self, label, size):
        t=Gtk.Label(label=(label or "?")[:1].upper()); t.set_size_request(S(size),S(size)); t.add_css_class("greeter-tile")
        t.add_css_class(f"tile-{sum(ord(c) for c in (label or '?'))%len(METRO_COLORS)}"); return t

    # ---------------------------------------------------------- the password
    def show_password(self, login, error="", typed="", same=False):
        self.user=login; full=dict(self.people).get(login,login)
        if not same or self.session not in [s["id"] for s in self.sessions]:   # this user's last session
            mine=self.memory.session(login)
            self.session=mine if any(s["id"]==mine for s in self.sessions) else loginscreen.default_session(self.sessions)
        if not same: self.digits=self.memory.keyboard(login)=="digits"   # the keyboard this user last logged in with
        clear_box(self.body); self.rows=[]; self.keys=[]; self.layer="lower"
        cols=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(60)); self.body.append(cols)
        left=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(10)); left.set_valign(Gtk.Align.START); cols.append(left)
        left.append(self.tile(full,190))
        n=Gtk.Label(label=full); n.add_css_class("greeter-user"); n.set_xalign(0); n.set_max_width_chars(16); n.set_wrap(True); left.append(n)
        if full!=login: m=Gtk.Label(label=login); m.add_css_class("muted"); m.set_xalign(0); left.append(m)
        right=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4)); right.set_halign(Gtk.Align.START); right.set_size_request(S(716),-1); cols.append(right)   # as wide as the full keyboard
        h=Gtk.Label(label="Password"); h.add_css_class("section-title"); h.set_xalign(0); right.append(h)
        self.entry=Gtk.PasswordEntry(); self.entry.add_css_class("password-field"); self.entry.set_show_peek_icon(True); self.entry.set_text(typed)
        self.entry.connect("activate",lambda *_:self.submit()); self.entry.set_margin_bottom(S(4)); right.append(self.entry)
        self.status=Gtk.Label(label=error or " "); self.status.add_css_class("greeter-status"); self.status.add_css_class("error" if error else "signing-in"); self.status.set_xalign(0); self.status.set_wrap(True)
        self.status.set_margin_bottom(S(6)); self.status.set_size_request(-1,S(30)); right.append(self.status)   # the same height with a message or without
        self.entry.connect("changed",lambda *_:self.clear_error())
        def line(widgets, homogeneous=True, fill=False):   # fill: as wide as the letter rows above
            box=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(4)); box.set_homogeneous(homogeneous)
            for w in widgets: box.append(w)
            box.set_margin_bottom(S(4)); box.set_halign(Gtk.Align.FILL if fill else Gtk.Align.START); right.append(box); self.rows.append(list(widgets))
        def key(label, handler, *css):
            b=Gtk.Button(label=label); b.add_css_class("key")
            for c in css: b.add_css_class(c)
            b.connect("clicked",lambda _b:handler()); return b
        if self.digits:
            for r in (("1","2","3"),("4","5","6"),("7","8","9")): line([key(d,lambda d=d:self.type(d),"pad") for d in r])
            line([key("⌫",self.erase,"pad"),key("0",lambda:self.type("0"),"pad"),key("ABC  Full keyboard",self.switch,"wide")],homogeneous=False)
        else:
            for r in range(4):
                made=[key("",lambda r=r,c=c:self.type(KEYS[self.layer][r][c]),"letter") for c in range(10)]   # square keys
                self.keys.append(made); line(made)
            line([key("⇧ Shift",lambda:self.set_layer("lower" if self.layer=="upper" else "upper"),"wide"),
                  key("&123",lambda:self.set_layer("lower" if self.layer=="symbols" else "symbols"),"wide"),
                  key("Space",lambda:self.type(" "),"wide"),key("⌫",self.erase,"wide"),key("123  Number pad",self.switch,"wide")],fill=True)
            self.label_keys()
        name=next((s["name"] for s in self.sessions if s["id"]==self.session),"No session")
        sess=Gtk.Button(); sl=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(12)); a=Gtk.Label(label="Session"); a.set_xalign(0); a.set_hexpand(True)
        sl.append(a); mark=tv_mark(24) if self.session.startswith("tvwcs-") else None
        if mark: sl.append(mark)
        v=Gtk.Label(label=name); v.add_css_class("setting-value"); sl.append(v); sess.set_child(sl); sess.connect("clicked",lambda *_:self.choose_session())
        sess.set_margin_top(S(10))
        go=Gtk.Button(label="Log in"); go.add_css_class("active"); go.connect("clicked",lambda *_:self.submit()); go.set_margin_top(S(10))
        actions=[sess]+([key("Back",lambda:self.show_users(login),"wide")] if len(self.people)>1 else [])+[go]
        box=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(6)); box.set_margin_top(S(10))
        sess.set_hexpand(True)
        for w in actions: w.set_margin_top(0); box.append(w)
        for w in actions[1:]: w.set_size_request(S(140),-1)
        right.append(box); self.rows.append(actions); self.go=go; self.rows.append(self.power)
        self.focus(self.rows[0][0])

    def clear_error(self):
        """Typing the next password takes the last error away."""
        if self.entry.get_text() and self.status.has_css_class("error"):
            self.status.remove_css_class("error"); self.status.add_css_class("signing-in"); self.status.set_text(" ")
    def label_keys(self):
        for r,row in enumerate(self.keys):
            for c,b in enumerate(row): b.set_label(KEYS[self.layer][r][c])
    def set_layer(self, layer): self.layer=layer; self.label_keys()
    def type(self, text):
        if self.busy: return
        self.entry.set_text(self.entry.get_text()+text)
        if self.layer=="upper": self.set_layer("lower")   # Shift is for one letter
    def erase(self):
        if not self.busy: self.entry.set_text(self.entry.get_text()[:-1])
    def switch(self):
        self.digits=not self.digits; self.show_password(self.user,typed=self.entry.get_text(),same=True)
        self.focus(self.rows[-3][-1])   # the switch key, on the other keyboard

    # ---------------------------------------------------------- logging in
    def submit(self):
        if self.busy or self.user is None: return
        session=next((s for s in self.sessions if s["id"]==self.session),None)
        if session is None: self.status.set_text("There is no session to start: install i3 or sway."); return
        self.busy=True; self.status.remove_css_class("error"); self.status.add_css_class("signing-in"); self.status.set_text("Logging in…")
        password=self.entry.get_text(); user=self.user; keyboard="digits" if self.digits else "full"
        cmd=loginscreen.start_session_argv(session)
        env=[f"XDG_SESSION_TYPE={session['kind']}"]+([f"XDG_CURRENT_DESKTOP={session['desktop']}",f"XDG_SESSION_DESKTOP={session['desktop']}"] if session.get("desktop") else [])
        def work():
            try: client=self.app.connect()
            except (OSError,greeter.GreetdError) as exc: return f"Could not reach greetd: {exc}"
            return greeter.log_in(client,user,password,cmd,env)
        def done(problem):
            self.busy=False
            if problem:
                self.entry.set_text(""); self.status.remove_css_class("signing-in"); self.status.add_css_class("error"); self.status.set_text(problem); return
            self.memory.remember(user,session["id"],keyboard)
            if self.app.demo: self.status.set_text(f"Logged in (demo): would start {session['name']}."); self.entry.set_text(""); return
            self.app.quit()   # greetd starts the session once the greeter has gone
            GLib.timeout_add_seconds(3,lambda:os._exit(0))   # gone even if something keeps GTK's main loop running
        threading.Thread(target=lambda:(lambda r:GLib.idle_add(lambda:(done(r),GLib.SOURCE_REMOVE)[1]))(work()),daemon=True).start()

    # ---------------------------------------------------------- dialogs
    def modal(self, title, message, buttons, back):
        """A card over the screen: buttons is [[(label, handler, css)]] (rows)."""
        clear_box(self.card); self.scrim.set_visible(True); self._return=self.get_focus()
        t=Gtk.Label(label=title); t.add_css_class("pane-title"); t.set_xalign(0); t.set_wrap(True); self.card.append(t)
        if message:
            m=Gtk.Label(label=message); m.add_css_class("muted"); m.set_xalign(0); m.set_wrap(True); m.set_margin_bottom(S(10)); self.card.append(m)
        self.modal_rows=[]
        for specs in buttons:
            box=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL if len(specs)>1 else Gtk.Orientation.VERTICAL,spacing=S(6)); box.set_homogeneous(True); made=[]
            for label,handler,css in specs:
                b=Gtk.Button(label=label)
                if css: b.add_css_class(css)
                b.connect("clicked",lambda _b,h=handler:h()); box.append(b); made.append(b)
            self.card.append(box); self.modal_rows.append(made)
        self.modal_back=back; self.focus(self.modal_rows[0][0])
    def close_modal(self):
        self.scrim.set_visible(False); self.modal_rows=None; self.modal_back=None
        back=getattr(self,"_return",None)
        if back is not None and usable(back): back.grab_focus()
        elif self.rows: self.focus(self.rows[0][0])
    def show_message(self, title, message):
        clear_box(self.body); t=Gtk.Label(label=title); t.add_css_class("greeter-title"); t.set_xalign(0); self.body.append(t)
        m=Gtk.Label(label=message); m.add_css_class("muted"); m.set_xalign(0); self.body.append(m); self.rows=[self.power]; self.focus(self.power[0])
    def choose_session(self):
        def pick(sid): self.session=sid; self.close_modal(); self.show_password(self.user,typed=self.entry.get_text(),same=True)
        rows=[[(("✓  " if s["id"]==self.session else "     ")+s["name"],lambda sid=s["id"]:pick(sid),None)] for s in self.sessions]
        self.modal("Session","What to start after logging in.",rows+[[("Cancel",self.close_modal,None)]],self.close_modal)
        current=next((i for i,s in enumerate(self.sessions) if s["id"]==self.session),0)
        self.focus(self.modal_rows[current][0])
    def ask_power(self, label, verb):
        question={"suspend":"Put the computer to sleep?","reboot":"Restart the computer?","poweroff":"Shut the computer down?"}[verb]
        def go():
            self.close_modal()
            if self.app.demo: print("Would run: systemctl",verb); return
            subprocess.Popen(["systemctl",verb],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.modal(label,question,[[("Cancel",self.close_modal,None),(label,go,"danger")]],self.close_modal)

    # ---------------------------------------------------------- the remote
    def focus(self, w):
        if w is not None:
            w.grab_focus(); GLib.timeout_add(80,lambda:(self.get_focus() is None and usable(w) and w.grab_focus(),GLib.SOURCE_REMOVE)[1])
    def _rows(self): return self.modal_rows if self.modal_rows is not None else self.rows
    def _where(self, rows, w):
        for i,row in enumerate(rows):
            for j,b in enumerate(row):
                if b is w or (w is not None and w.is_ancestor(b)): return i,j
        return None
    def _centre(self, w):
        ok,b=w.compute_bounds(self)
        return b.get_x()+b.get_width()/2 if ok else 0
    def move(self, dy, dx):
        rows=[[w for w in row if usable(w)] for row in self._rows()]; rows=[r for r in rows if r]
        if not rows: return True
        here=self._where(rows,self.get_focus())
        if here is None: self.focus(rows[0][0]); return True
        i,j=here
        if dx:
            k=j+dx
            if 0<=k<len(rows[i]): self.focus(rows[i][k])
            return True
        k=i+dy
        if not 0<=k<len(rows):
            if self.modal_rows is None: return True
            k%=len(rows)   # a dialog's list wraps around
        x=self._centre(rows[i][j]); self.focus(min(rows[k],key=lambda w:abs(self._centre(w)-x))); return True
    def key_pressed(self, _c, keyval, _code, state):
        if keyval in (Gdk.KEY_Up,Gdk.KEY_Down,Gdk.KEY_Left,Gdk.KEY_Right):
            self.typed=False
            if isinstance(self.get_focus(),Gtk.Text) and keyval in (Gdk.KEY_Left,Gdk.KEY_Right): return False
            return self.move(-1 if keyval==Gdk.KEY_Up else 1 if keyval==Gdk.KEY_Down else 0,-1 if keyval==Gdk.KEY_Left else 1 if keyval==Gdk.KEY_Right else 0)
        if keyval in (Gdk.KEY_Escape,Gdk.KEY_Back):
            if self.modal_rows is not None: (self.modal_back or self.close_modal)()
            elif self.user is not None and len(self.people)>1: self.show_users(self.user)
            return True
        if self.modal_rows is not None or self.user is None or self.busy: return False
        if isinstance(self.get_focus(),Gtk.Text): return False   # the field itself has the keyboard
        if keyval==Gdk.KEY_BackSpace: self.erase(); return True
        if keyval in (Gdk.KEY_Return,Gdk.KEY_KP_Enter,Gdk.KEY_ISO_Enter):
            if self.typed: self.submit(); return True
            return False   # presses the selected key or button
        ch=Gdk.keyval_to_unicode(keyval)
        if ch>=32 and chr(ch).isprintable() and not state&(Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.ALT_MASK):
            if self.digits and not chr(ch).isdigit(): return True
            self.entry.set_text(self.entry.get_text()+chr(ch)); self.typed=True; return True
        return False

class GreeterApp(Gtk.Application):
    def __init__(self, demo=False):
        super().__init__(application_id=APP_ID+(".Demo" if demo else ""),flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.demo=demo; self.look=loginscreen.read_look(); self.clock_24h=False
        self.state_dir=os.path.join(GLib.get_user_cache_dir(),"tvwcs-greeter-demo") if demo else None
    def connect(self): return DemoGreetd() if self.demo else greeter.Greetd()
    def do_activate(self):
        set_scale(effective_scale(self.look["scale"],screen_height()))
        css=Gtk.CssProvider(); css.load_from_data(render_css(self.look["accent"],effective_scale(self.look["scale"],screen_height()),GREETER_CSS,self.look["theme"]).encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme",self.look["theme"]=="dark")
        w=GreeterWindow(self)
        if self.demo and os.environ.get("TVWCS_GREETER_WINDOWED"): w.set_default_size(1920,1080)
        else: w.fullscreen()
        w.present()

def main(argv=None):
    argv=sys.argv[1:] if argv is None else argv
    return GreeterApp(demo="--demo" in argv).run([sys.argv[0]])

if __name__=="__main__": sys.exit(main())
