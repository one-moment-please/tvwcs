"""Profile editing windows (ordinary dialogs, opened from the Guide)."""
from __future__ import annotations
import uuid
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from tvwcs.model import (DIALOG_PREFIX, LAUNCH_NEW_WORKSPACE, LAUNCH_SAME, MAX_DESCRIPTION, PIN_SCOPE_LABELS, PIN_SCOPES,
                   LaunchProfile, profile_detail)
from tvwcs.pinlock import make_hash, valid_pin
from tvwcs.widgets import S, clear_box, section_title

def _page(window):
    box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(10)); box.add_css_class("tvwcs-root")
    box.set_margin_top(S(18)); box.set_margin_bottom(S(18)); box.set_margin_start(S(20)); box.set_margin_end(S(20)); window.set_child(box); return box

class ProfileEditor(Gtk.Window):
    def __init__(self, app, existing, application):
        super().__init__(application=app,title=f"{DIALOG_PREFIX}Launch Profile",modal=True,transient_for=app.window)
        self.app=app; self.existing=existing; self.application=application
        default=app.default_profile(application) if application else None
        self.primary=existing is not None and default is not None and default.id==existing.id   # the app's main profile
        self.add_css_class("tvwcs-window"); self.set_default_size(S(560),S(640)); self.set_resizable(False)
        box=_page(self)
        title=Gtk.Label(label=f"Launch profile · {application.name if application else existing.desktop_id}"); title.set_xalign(0); title.add_css_class("brand"); box.append(title)
        scroll=Gtk.ScrolledWindow(); scroll.set_vexpand(True); scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC); box.append(scroll)
        form=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(10)); form.set_margin_end(S(12)); scroll.set_child(form)
        self.name_entry=self._field(form,"Profile name",existing.name if existing else application.name)
        self.channel_entry=self._field(form,"Channel number (1–999, optional)",str(existing.channel) if existing and existing.channel is not None else "")
        self.command_entry=self._field(form,"Custom launch command (optional)",existing.command if existing else "")
        self.action_ids=[("", "None — standard launcher")]
        if application: self.action_ids.extend(application.desktop_actions)
        action_wrap=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4)); action_label=Gtk.Label(label=".desktop action (optional)"); action_label.set_xalign(0); action_wrap.append(action_label)
        self.action_dropdown=Gtk.DropDown.new_from_strings([name for _id,name in self.action_ids]); action_wrap.append(self.action_dropdown); form.append(action_wrap)
        selected=existing.desktop_action if existing else ""
        self.action_dropdown.set_selected(next((i for i,(aid,_n) in enumerate(self.action_ids) if aid==selected),0))
        self.description_entry=None
        if not self.primary:   # the main profile is described by its application (set on the application's own page)
            self.description_entry=self._field(form,"Description (optional)",existing.description if existing else "")
            self.description_entry.set_placeholder_text(profile_detail(existing,application) if existing and profile_detail(existing,application) else "Defaults to the launch options: the action and command above")
            self._hint(form,"Shown beside the profile's name in the Guide. Leave empty to show its launch options.")
        self.workspace_check=Gtk.CheckButton(label="Always launch in a new workspace (hides other apps)")
        self.workspace_check.set_active(bool(existing) and existing.launch_mode==LAUNCH_NEW_WORKSPACE); form.append(self.workspace_check)
        self._hint(form,"Unchecked, the app opens tiled in the current workspace. You can also flip this from the icon beside the app's name in the Quick Menu.")
        self._hint(form,"Leave the command empty to use the app's normal Linux launcher. Custom commands are split into arguments and run without a shell.")
        # ---- PIN protection
        form.append(section_title("PIN PROTECTION")); has_pin=bool(existing and existing.pin_hash)
        self.current_pin=self.remove_check=None
        if has_pin:
            self.current_pin=self._secret(form,"Current PIN (needed to change or delete this profile)")
            self.remove_check=Gtk.CheckButton(label="Remove the PIN"); form.append(self.remove_check)
        self.new_pin=self._secret(form,"New PIN, 4–8 digits" if not has_pin else "New PIN (leave empty to keep the current one)")
        self.confirm_pin=self._secret(form,"Repeat the new PIN")
        scope_wrap=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4)); lab=Gtk.Label(label="Ask for the PIN"); lab.set_xalign(0); scope_wrap.append(lab)
        self.scope_dropdown=Gtk.DropDown.new_from_strings([PIN_SCOPE_LABELS[k] for k in PIN_SCOPES]); scope_wrap.append(self.scope_dropdown); form.append(scope_wrap)
        self.scope_dropdown.set_selected(PIN_SCOPES.index(existing.pin_scope) if existing and existing.pin_scope in PIN_SCOPES else 0)
        self._hint(form,"This is a convenience lock for a shared TV, not strong security: someone who can edit TVWCS's config file can remove it.")
        self.error=Gtk.Label(label=""); self.error.set_xalign(0); self.error.set_wrap(True); self.error.add_css_class("error"); box.append(self.error)
        buttons=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(6)); buttons.set_halign(Gtk.Align.END); box.append(buttons)
        if existing:
            delete=Gtk.Button(label="Delete profile"); delete.connect("clicked",self._delete); buttons.append(delete)
        cancel=Gtk.Button(label="Cancel"); cancel.connect("clicked",lambda *_:self.close()); buttons.append(cancel)
        save=Gtk.Button(label="Save"); save.add_css_class("active"); save.connect("clicked",self._save); buttons.append(save)
    def _field(self,parent,label,value):
        wrap=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4)); lab=Gtk.Label(label=label); lab.set_xalign(0); wrap.append(lab); entry=Gtk.Entry(); entry.set_text(value); wrap.append(entry); parent.append(wrap); return entry
    def _secret(self,parent,label):
        wrap=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4)); lab=Gtk.Label(label=label); lab.set_xalign(0); wrap.append(lab); entry=Gtk.PasswordEntry(); entry.set_show_peek_icon(True); wrap.append(entry); parent.append(wrap); return entry
    @staticmethod
    def _hint(parent,text):
        h=Gtk.Label(label=text); h.set_xalign(0); h.set_wrap(True); h.add_css_class("muted"); parent.append(h)

    def _authorise(self):
        """Changing or deleting a protected profile needs its current PIN, or the lock could simply be edited away."""
        if self.existing and self.existing.pin_hash:
            status,wait=self.app.pin_gate.attempt(self.existing.id,self.current_pin.get_text(),self.existing.pin_hash)
            if status=="wrong": raise ValueError("That is not the profile's current PIN.")
            if status=="locked": raise ValueError(f"Too many wrong tries. Try again in {wait} seconds.")
    def _pin_settings(self):
        scope=PIN_SCOPES[self.scope_dropdown.get_selected()]
        pin_hash=self.existing.pin_hash if self.existing else ""
        if self.remove_check is not None and self.remove_check.get_active(): pin_hash=""
        new,again=self.new_pin.get_text(),self.confirm_pin.get_text()
        if new or again:
            if not valid_pin(new): raise ValueError("A PIN is 4 to 8 digits.")
            if new!=again: raise ValueError("The two PINs do not match.")
            pin_hash=make_hash(new)
        return pin_hash,scope
    def _save(self,*_):
        try:
            raw=self.channel_entry.get_text().strip(); channel=int(raw) if raw else None
            mode=LAUNCH_NEW_WORKSPACE if self.workspace_check.get_active() else LAUNCH_SAME
            self._authorise(); pin_hash,scope=self._pin_settings()
            description=self.description_entry.get_text() if self.description_entry is not None else (self.existing.description if self.existing else "")
            profile=LaunchProfile(id=self.existing.id if self.existing else str(uuid.uuid4()),desktop_id=self.existing.desktop_id if self.existing else self.application.desktop_id,
                                  name=self.name_entry.get_text().strip(),command=self.command_entry.get_text().strip(),channel=channel,
                                  favorite=self.existing.favorite if self.existing else False,launch_mode=mode,
                                  desktop_action=self.action_ids[self.action_dropdown.get_selected()][0],pin_hash=pin_hash,pin_scope=scope,description=description)
            self.app.store.set_profile(profile)
            self.app.refresh_data(rebuild=True); self.close()
        except (ValueError,TypeError) as exc: self.error.set_text(str(exc))
    def _delete(self,*_):
        try: self._authorise()
        except ValueError as exc: self.error.set_text(str(exc)); return
        self.app.store.delete(self.existing.id); self.app.refresh_data(rebuild=True); self.close()

class ApplicationProfilesWindow(Gtk.Window):
    def __init__(self, app, desktop_id):
        application=app.catalogue.by_id().get(desktop_id)
        super().__init__(application=app,title=f"{DIALOG_PREFIX}{application.name if application else desktop_id}",modal=True,transient_for=app.window)
        self.app=app; self.desktop_id=desktop_id; self.application=application
        self.add_css_class("tvwcs-window"); self.set_default_size(S(540),S(460)); self.set_resizable(False)
        box=_page(self)
        title=Gtk.Label(label=f"Application profiles · {application.name if application else desktop_id}"); title.set_xalign(0); title.add_css_class("brand"); box.append(title)
        default_text=(application.comment or application.generic_name or "") if application else ""
        box.append(Gtk.Label(label="Description")); box.get_last_child().set_xalign(0)
        self.description_entry=Gtk.Entry(); self.description_entry.set_text(app.store.app_descriptions.get(desktop_id,"")); self.description_entry.set_max_length(MAX_DESCRIPTION)
        self.description_entry.set_placeholder_text(default_text or "No description in the application's .desktop file")
        self.description_entry.connect("activate",lambda *_:self._save_description()); box.append(self.description_entry)
        hint=Gtk.Label(label="Shown beside the application's name in the Guide. Leave empty to use the description from its .desktop file (above). Press Enter or close this window to keep a change."); hint.set_xalign(0); hint.set_wrap(True); hint.add_css_class("muted"); box.append(hint)
        self.connect("close-request",lambda *_:(self._save_description(),False)[1])
        scroll=Gtk.ScrolledWindow(); scroll.set_vexpand(True); scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC); box.append(scroll)
        self.rows=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=S(4)); scroll.set_child(self.rows); self._refresh_rows()
        buttons=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(6)); buttons.set_halign(Gtk.Align.END); box.append(buttons)
        add=Gtk.Button(label="+"); add.set_tooltip_text("Add launch profile"); add.connect("clicked",self._add); buttons.append(add)
        close=Gtk.Button(label="Close"); close.connect("clicked",lambda *_:self.close()); buttons.append(close)
    def _refresh_rows(self):
        clear_box(self.rows)
        for profile in self.app.store.for_app(self.desktop_id):
            row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=S(8)); label=Gtk.Label(label=profile.name); label.set_xalign(0); label.set_hexpand(True); row.append(label)
            where=Gtk.Label(label="New workspace" if profile.launch_mode==LAUNCH_NEW_WORKSPACE else "Tiled"); where.add_css_class("muted"); row.append(where)
            edit=Gtk.Button(label="Edit"); edit.connect("clicked",lambda _b,p=profile:self._edit(p)); row.append(edit); self.rows.append(row)
    def _add(self,*_):
        if not self.application: return
        editor=ProfileEditor(self.app,None,self.application); editor.name_entry.set_text(f"{self.application.name} profile {len(self.app.store.for_app(self.desktop_id))+1}")
        editor.present(); editor.connect("close-request",lambda *_: (self._refresh_after_editor(),False)[1])
    def _edit(self,profile):
        editor=ProfileEditor(self.app,profile,self.application); editor.present(); editor.connect("close-request",lambda *_: (self._refresh_after_editor(),False)[1])
    def _save_description(self):
        text=" ".join(self.description_entry.get_text().split())
        if text!=self.app.store.app_descriptions.get(self.desktop_id,""):
            self.app.store.set_app_description(self.desktop_id,text); self.app.refresh_data(rebuild=True)
    def _refresh_after_editor(self):
        self.app.refresh_data(rebuild=True); self._refresh_rows()
