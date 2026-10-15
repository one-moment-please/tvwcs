"""Editing launch profiles inside the TVWCS window, with the remote: every field is a row that opens the on-screen
keyboard, the number keypad, a list of choices or the hotkey capture. Nothing is stored until Save."""
from __future__ import annotations
from dataclasses import replace

from tvwcs.model import LAUNCH_NEW_WORKSPACE, MAX_DESCRIPTION, PIN_SCOPE_LABELS, PIN_SCOPES, profile_detail
from tvwcs.hotkeys import describe
from tvwcs.profile_draft import ProfileDraft, default_name

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from tvwcs.widgets import NavGroup, S, glyph, muted_label

def _row(win, label, value, handler, icon=None, fallback=""):
    """A field: its name on the left, its value under it. Enter opens what changes it."""
    b=Gtk.Button(); b.add_css_class("dialog-button"); b.add_css_class("field-row")
    line=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(12))
    if icon: line.append(glyph(icon,fallback,22))
    text=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0); text.set_hexpand(True)
    name=Gtk.Label(label=label); name.set_xalign(0); name.set_ellipsize(3); name.set_max_width_chars(24); text.append(name)
    v=Gtk.Label(label=value); v.add_css_class("field-value"); v.set_xalign(0); v.set_ellipsize(3); v.set_max_width_chars(24); text.append(v)   # long values do not widen the card
    line.append(text); b.set_child(line); b.connect("clicked",lambda *_:handler()); return b

class ProfileEditor:
    """One launch profile, drawn in the TVWCS window's dialog card. `back` runs after Save, Delete or Cancel
    (the application's profile list when opened from there)."""
    def __init__(self, win, existing, application, back=None, name=None):
        self.win=win; self.app=win.app; self.existing=existing; self.application=application; self.back=back
        default=self.app.default_profile(application) if application else None
        self.primary=existing is not None and default is not None and default.id==existing.id
        self.draft=ProfileDraft.of(existing) if existing else ProfileDraft.new(application.desktop_id,name or default_name(application,len(self.app.store.for_app(application.desktop_id))))
        self.start=replace(self.draft); self.error=""; self.focus_key="name"

    def open(self):
        """A profile protected by a PIN asks for it before it can be changed or deleted."""
        if self.existing is not None and self.existing.pin_hash: self.win.ask_pin(self.existing,self.show)
        else: self.show()

    def _done(self):
        self.win.close_modal()
        if self.back: self.back()
    def _cancel(self):
        if self.draft!=self.start:
            self.win.confirm("Discard changes?","The changes to this profile have not been saved.","Discard",self._done,back=self.show)
        else: self._done()

    def show(self):
        win=self.win; d=self.draft; app=self.application
        win._begin_modal(); win._title(f"{'Edit' if self.existing else 'New'} profile · {app.name if app else d.desktop_id}")
        if self.error:
            e=Gtk.Label(label=self.error); e.add_css_class("error"); e.set_wrap(True); e.set_xalign(0); e.set_margin_bottom(S(6)); win.modal_card.append(e)
        scroll=Gtk.ScrolledWindow(); scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC); scroll.set_propagate_natural_height(True)
        scroll.set_max_content_height(max(S(260),win.get_height()-S(330)))
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(2)); scroll.set_child(box); win.modal_card.append(scroll)
        actions=dict(app.desktop_actions) if app else {}
        rows=[("name","Name",d.name or "(none)",self._edit_name),
              ("channel","Channel number",f"{int(d.channel):03d}" if d.channel.strip().isdigit() else "None",self._edit_channel),
              ("opens","Opens",("In a workspace of its own" if d.new_workspace else "Next to the other apps"),self._edit_opens),
              ("hotkey","Hotkey",describe(d.hotkey) if d.hotkey else "None",self._edit_hotkey)]
        if actions: rows.append(("action","Starts with",actions.get(d.action,"The usual way") if d.action else "The usual way",self._edit_action))
        rows.append(("command","Custom command",d.command or "None: the application's own launcher",self._edit_command))
        if not self.primary:
            shown=d.description or (profile_detail(self.draft.profile(),app) if d.channel.strip().isdigit() or not d.channel.strip() else "")
            rows.append(("description","Description",d.description or (f"Shows its launch options{': '+shown if shown else ''}"),self._edit_description))
        rows.append(("pin","PIN lock","On" if d.pin_hash else "Off",self._edit_pin))
        if d.pin_hash: rows.append(("scope","Ask for the PIN",PIN_SCOPE_LABELS[d.pin_scope],self._edit_scope))
        groups=[]; focus=None
        for key,label,value,handler in rows:
            b=_row(win,label,value,lambda h=handler,k=key:(setattr(self,"focus_key",k),h())); box.append(b); groups.append(NavGroup([b]))
            if key==self.focus_key: focus=b
        buttons=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(6)); buttons.set_homogeneous(True); buttons.set_margin_top(S(10))
        save=Gtk.Button(label="Save"); save.add_css_class("active"); save.connect("clicked",lambda *_:self._save())
        cancel=Gtk.Button(label="Cancel"); cancel.connect("clicked",lambda *_:self._cancel())
        line=[save,cancel]
        if self.existing is not None:
            delete=Gtk.Button(label="Delete"); delete.add_css_class("danger"); delete.connect("clicked",lambda *_:self._delete()); line.append(delete)
        for b in line: buttons.append(b)
        win.modal_card.append(buttons); groups.append(NavGroup(line))
        if self.focus_key=="save": focus=save
        win._modal_groups=groups; win._modal_back=self._cancel; (focus or groups[0][0]).grab_focus()

    # ---- the fields
    def _edit_name(self):
        def got(text): self.draft.name=text.strip() or self.draft.name; self.show()
        self.win.ask_text("Profile name",got,self.draft.name,back=self.show,max_len=80)
    def _edit_channel(self):
        def got(text): self.draft.channel=text.strip(); self.show()
        self.win.ask_channel("Channel number",got,self.draft.channel,back=self.show)
    def _edit_opens(self):
        def got(k): self.draft.new_workspace=k=="new"; self.show()
        self.win.choose_option("Opens",[("same","Next to the other apps (tiled)"),("new","In a workspace of its own")],
                               "new" if self.draft.new_workspace else "same",got,back=self.show)
    def _edit_hotkey(self):
        def got(spec): self.draft.hotkey=spec; self.show()
        self.win.assign_hotkey(("profile",self.draft.id),self.draft.name or "this profile",got,back=self.show)
    def _edit_action(self):
        options=[("","The usual way")]+list(self.application.desktop_actions)
        def got(k): self.draft.action=k; self.show()
        self.win.choose_option("Starts with",options,self.draft.action,got,back=self.show)
    def _edit_command(self):
        def got(text): self.draft.command=text.strip(); self.show()
        self.win.ask_text("Custom command",got,self.draft.command,"Runs instead of the application's own launcher, without a shell. Leave empty to use the launcher.",
                          back=self.show)
    def _edit_description(self):
        def got(text): self.draft.description=" ".join(text.split()); self.show()
        self.win.ask_text("Description",got,self.draft.description,"Shown beside the name in Applications. Leave empty to show its launch options.",
                          back=self.show,max_len=MAX_DESCRIPTION)
    def _edit_pin(self):
        options=[("set","Change the PIN" if self.draft.pin_hash else "Set a PIN")]
        if self.draft.pin_hash: options.append(("remove","Remove the PIN"))
        def got(k):
            if k=="remove": self.draft.pin_hash=""; self.error=""; self.show(); return
            self._ask_new_pin()
        self.win.choose_option("PIN lock",options,None,got,back=self.show)
    def _ask_new_pin(self):
        def first(new):
            def second(again):
                try: self.draft.set_pin(new,again); self.error=""
                except ValueError as exc: self.error=str(exc)
                self.show()
            self.win.ask_text("Repeat the new PIN",second,"",back=self.show,digits=True,secret=True,max_len=8)
        self.win.ask_text("New PIN",first,"","4 to 8 digits. This keeps others on a shared TV out; it is not strong security.",
                          back=self.show,digits=True,secret=True,max_len=8)
    def _edit_scope(self):
        def got(k): self.draft.pin_scope=k; self.show()
        self.win.choose_option("Ask for the PIN",[(k,PIN_SCOPE_LABELS[k]) for k in PIN_SCOPES],self.draft.pin_scope,got,back=self.show)

    # ---- storing
    def _save(self):
        self.focus_key="save"
        try:
            self.app.store.set_profile(self.draft.profile())
        except (ValueError,TypeError) as exc:
            self.error=str(exc); self.show(); return
        self.app.apply_hotkeys(); self.win.close_modal(); self.app.refresh_data(rebuild=True)
        if self.back: self.back()
    def _delete(self):
        def gone():
            self.app.store.delete(self.existing.id); self.app.apply_hotkeys(); self.app.refresh_data(rebuild=True)
            if self.back: self.back()
        self.win.confirm("Delete profile?",f"Delete “{self.existing.name}”? This cannot be undone.","Delete",gone,back=self.show)

class ApplicationProfiles:
    """An application's description and its launch profiles: edit one, or add another."""
    def __init__(self, win, desktop_id):
        self.win=win; self.app=win.app; self.desktop_id=desktop_id; self.application=self.app.catalogue.by_id().get(desktop_id)

    def show(self, focus_id=None):
        win=self.win; app=self.application; store=self.app.store
        win._begin_modal(); win._title(app.name if app else self.desktop_id)
        groups=[]; focus=None
        own=store.app_descriptions.get(self.desktop_id,"")
        default_text=(app.comment or app.generic_name or "") if app else ""
        b=_row(win,"Description",own or default_text or "None",self._edit_description); win.modal_card.append(b); groups.append(NavGroup([b]))
        if focus_id=="description": focus=b
        head=muted_label("Launch profiles"); head.set_margin_top(S(8)); win.modal_card.append(head)
        scroll=Gtk.ScrolledWindow(); scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC); scroll.set_propagate_natural_height(True)
        scroll.set_max_content_height(max(S(220),win.get_height()-S(400)))
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(2)); scroll.set_child(box); win.modal_card.append(scroll)
        for p in store.for_app(self.desktop_id):
            where="In a workspace of its own" if p.launch_mode==LAUNCH_NEW_WORKSPACE else "Next to the other apps"
            value=(f"Channel {p.channel:03d} · " if p.channel is not None else "")+where+(" · PIN" if p.pin_hash else "")
            r=_row(win,p.name,value,lambda prof=p:self._edit(prof)); box.append(r); groups.append(NavGroup([r]))
            if p.id==focus_id: focus=r
        line=[]
        if app is not None:
            add=Gtk.Button(label="Add a profile"); add.connect("clicked",lambda *_:self._add()); line.append(add)
        close=Gtk.Button(label="Close"); close.connect("clicked",lambda *_:win.close_modal()); line.append(close)
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(6)); row.set_homogeneous(True); row.set_margin_top(S(10))
        for x in line: row.append(x)
        win.modal_card.append(row); groups.append(NavGroup(line))
        win._modal_groups=groups; win._modal_back=win.close_modal; (focus or groups[min(1,len(groups)-1)][0]).grab_focus()

    def _edit(self, profile):
        ProfileEditor(self.win,self.app.store.get(profile.id) or profile,self.application,back=lambda pid=profile.id:self.show(pid)).open()
    def _add(self):
        ProfileEditor(self.win,None,self.application,back=self.show).open()
    def _edit_description(self):
        def got(text):
            text=" ".join(text.split())
            if text!=self.app.store.app_descriptions.get(self.desktop_id,""):
                self.app.store.set_app_description(self.desktop_id,text); self.win.close_modal(); self.app.refresh_data(rebuild=True)
            self.show("description")
        app=self.application; default_text=(app.comment or app.generic_name or "") if app else ""
        self.win.ask_text("Description",got,self.app.store.app_descriptions.get(self.desktop_id,""),
                          "Shown beside the name in Applications. Leave empty to use the application's own: "+(default_text or "(none)"),
                          back=lambda:self.show("description"),max_len=MAX_DESCRIPTION)
