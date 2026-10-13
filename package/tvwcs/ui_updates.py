"""The Updates tab of the Applications window: a GUI over apt.

Layout (as required):
  * a top bar with "Check for updates" (becomes "Refresh" once used), "Install updates",
    "Clear" (unchecks everything) and "Select all" (checks everything);
  * below it, split left/right — the left list (about 2/3 as wide as the right panel) shows one row
    per pending upgrade: its kind (Security update / Software update / 3rd party repository update),
    a checkbox deciding whether it is installed when "Install updates" is pressed, then the package
    name, new version and size;
  * the right panel shows details of the selected package: description, information, packages
    affected and changelog.

apt calls run in a background thread so the interface never freezes; sudo failures are reported in
the status line instead of raising."""
from __future__ import annotations
import threading
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Pango

from tvwcs import updates
from tvwcs.widgets import NavGroup, S, clear_box, muted_label, section_title

KIND_LABELS = {"security": "Security update", "software": "Software update", "thirdparty": "3rd party repository update"}


class UpdatesTab(Gtk.Box):
    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=S(8))
        self.win = win
        self.app = win.app
        self.add_css_class("pane")
        self.set_margin_start(S(24)); self.set_margin_end(S(24)); self.set_margin_bottom(S(16))
        self._items = []                 # [{'package','current','candidate','size','kind','check','row',...}]
        self._checked = set()            # package names ticked for installation
        self._selected = None            # package name whose details are shown
        self._busy = False
        self._scanned = False
        self._build_shell()
        if updates.apt_available():
            self._load_list()

    # ------------------------------------------------------------- shell
    def _build_shell(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=S(6)); bar.set_margin_top(S(6))
        self.check_button = Gtk.Button(label="Check for updates")
        self.check_button.connect("clicked", self._on_check)
        self.install_button = Gtk.Button(label="Install updates")
        self.install_button.connect("clicked", self._on_install)
        self.clear_button = Gtk.Button(label="Clear")
        self.clear_button.connect("clicked", self._on_clear)
        self.select_all_button = Gtk.Button(label="Select all")
        self.select_all_button.connect("clicked", self._on_select_all)
        for b in (self.check_button, self.install_button, self.clear_button, self.select_all_button):
            bar.append(b)
        self.spinner = Gtk.Spinner(); self.status = Gtk.Label(label=""); self.status.set_xalign(0)
        self.status.add_css_class("muted"); self.status.set_hexpand(True); self.status.set_ellipsize(3)
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=S(8)); status_box.append(self.spinner); status_box.append(self.status)
        status_box.set_visible(False)
        bar.append(status_box)
        self.status_box = status_box
        self.append(bar)
        self.error_banner = muted_label(""); self.error_banner.add_css_class("error"); self.error_banner.set_visible(False)
        self.append(self.error_banner)

        split = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=S(12)); split.set_vexpand(True)
        left_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=S(4)); left_wrap.set_hexpand(True)
        left_wrap.set_size_request(S(360), -1)
        left_wrap.append(section_title("AVAILABLE UPDATES"))
        self.list_scroll = Gtk.ScrolledWindow(); self.list_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.list_scroll.set_vexpand(True); left_wrap.append(self.list_scroll)
        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=S(2)); self.list_scroll.set_child(self.list_box)
        self.summary = muted_label(""); left_wrap.append(self.summary)

        right_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=S(4)); right_wrap.set_hexpand(True)
        right_wrap.set_size_request(S(540), -1)   # the left column ends up about 2/3 as wide as this one
        right_wrap.append(section_title("PACKAGE DETAILS"))
        self.details_scroll = Gtk.ScrolledWindow(); self.details_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.details_scroll.set_vexpand(True); right_wrap.append(self.details_scroll)
        self.details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=S(6)); self.details_box.set_margin_end(S(6))
        self.details_scroll.set_child(self.details_box)
        self._show_details_placeholder()

        split.append(left_wrap); split.append(right_wrap)
        self.append(split)
        self.win._register("guide", self.check_button, self.install_button, self.clear_button, self.select_all_button)

    def _show_details_placeholder(self):
        clear_box(self.details_box)
        self.details_box.append(muted_label("Select a package on the left to see its description, information, the packages it affects and its changelog."))

    def _set_busy(self, busy, text=""):
        self._busy = busy
        self.status_box.set_visible(busy)
        if busy:
            self.spinner.start(); self.status.set_text(text or "Working…")
        else:
            self.spinner.stop()
        for b in (self.check_button, self.install_button):
            b.set_sensitive(not busy)

    def _error(self, text):
        self.error_banner.set_text(text); self.error_banner.set_visible(bool(text))

    def _async(self, work, done):
        def runner():
            try:
                result = work()
            except Exception as exc:                       # never let a worker thread die silently
                result = ("error", str(exc))
            GLib.idle_add(lambda: self._finish(done, result))
        self._set_busy(True)
        threading.Thread(target=runner, daemon=True).start()

    def _finish(self, done, result):
        self._set_busy(False)
        if isinstance(result, tuple) and result and result[0] == "error":
            self._error(result[1])
            return
        done(result)

    # ------------------------------------------------------------- data
    def _load_list(self):
        """Read the already-downloaded apt lists (fast, no sudo)."""
        def done(items):
            self._items = items
            self._reclassify(items)
            self._rebuild_rows()
        self._async(updates.list_upgrades, done)

    def _reclassify(self, items):
        origins = updates.read_sources_origin_map()
        for item in items:
            _, policy = __import__("tvwcs.network", fromlist=["run"]).run(["apt-cache", "policy", item["package"]])
            m = __import__("re").search(r"^\s+\*\*\s+(\S+)", policy, __import__("re").M)
            origin = m.group(1) if m else ""
            item["origin"] = origin
            item["kind"] = updates.classify(item["package"], item["candidate"], origin, " ".join(origins))

    def rebuild(self):
        """Called by the parent when the tab is (re)opened."""
        self._load_list()

    def _rebuild_rows(self):
        clear_box(self.list_box)
        groups = []
        if not self._items:
            self.list_box.append(muted_label("No pending updates. Press “Check for updates” to refresh the list from your repositories."))
            self.summary.set_text("")
            self._sync_nav(groups)
            return
        for item in self._items:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=S(8))
            check = Gtk.CheckButton()
            check.set_active(item["package"] in self._checked)
            check.connect("toggled", lambda _c, name=item["package"]: self._toggle_item(name))
            row.append(check)
            kind = Gtk.Label(label=KIND_LABELS.get(item["kind"], "Software update"))
            kind.add_css_class("update-kind"); kind.set_width_chars(16); kind.set_xalign(0)
            row.append(kind)
            name = Gtk.Label(label=item["package"]); name.set_xalign(0); name.set_ellipsize(3); name.set_max_width_chars(24)
            row.append(name)
            version = Gtk.Label(label=f"→ {item['candidate']}" if item["candidate"] else "")
            version.add_css_class("muted"); version.set_ellipsize(3); version.set_max_width_chars(22)
            row.append(version)
            size = Gtk.Label(label=item.get("size", "")); size.add_css_class("muted")
            row.append(size)
            main = Gtk.Button(); main.set_child(row); main.add_css_class("launch-row"); main.set_hexpand(True)
            main.connect("clicked", lambda _b, i=item: self._select(i))
            if item["package"] == self._selected:
                main.add_css_class("tvwcs-selected")
            self.list_box.append(main)
            groups.append(NavGroup([check, main], entry=main))
        checked_items = [i for i in self._items if i["package"] in self._checked]
        total = updates.download_size_label(checked_items) if checked_items else "—"
        self.summary.set_text(f"{len(self._items)} updates · {len(checked_items)} selected · {total}")
        self._sync_nav(groups)

    def _sync_nav(self, groups):
        for g in groups:
            self.win._groups["guide"].append(g)

    # ------------------------------------------------------------- top-bar actions
    def _on_check(self, button):
        self._error("")
        def done(result):
            ok, message = result
            if not ok:
                self._error(message or "apt update failed.")
            self.check_button.set_label("Refresh")
            self._scanned = True
            self._load_list()
        self._async(updates.refresh_lists, done)

    def _on_install(self, *_):
        selected = [i["package"] for i in self._items if i["package"] in self._checked]
        if not selected:
            self._error("Nothing is selected. Tick the updates you want to install."); return
        count = len(selected)
        def done(result):
            ok, message = result
            if ok:
                self._checked.clear()
                self._error("")
                self.win.notify_message(f"{count} update(s) installed.") if hasattr(self.win, "notify_message") else None
                self._load_list()
            else:
                self._error(message or "Installation failed.")
        self._async(lambda: updates.install_selected(selected), done)

    def _on_clear(self, *_):
        self._checked.clear()
        for item in self._items:
            item.pop("_check", None)
        self._rebuild_rows()

    def _on_select_all(self, *_):
        self._checked = {i["package"] for i in self._items}
        self._rebuild_rows()

    def _toggle_item(self, name):
        if name in self._checked:
            self._checked.discard(name)
        else:
            self._checked.add(name)
        checked_items = [i for i in self._items if i["package"] in self._checked]
        total = updates.download_size_label(checked_items) if checked_items else "—"
        self.summary.set_text(f"{len(self._items)} updates · {len(checked_items)} selected · {total}")

    # ------------------------------------------------------------- selection & details
    def _select(self, item):
        self._selected = item["package"]
        for child in self.list_box:
            pass
        self._rebuild_rows()
        clear_box(self.details_box)
        self.details_box.append(muted_label(f"Loading details for {item['package']}…"))
        def done(info):
            if self._selected != item["package"]:
                return
            self._fill_details(item, info)
        self._async(lambda: updates.package_info(item["package"]), done)

    def _fill_details(self, item, info):
        clear_box(self.details_box)
        title = Gtk.Label(label=item["package"]); title.add_css_class("pane-title"); title.set_xalign(0)
        self.details_box.append(title)
        versions = f"{item.get('current') or info.get('installed') or '—'}  →  {item['candidate'] or info.get('candidate') or '—'}"
        self.details_box.append(self._kv("Version", versions))
        self.details_box.append(self._kv("Kind", KIND_LABELS.get(item.get("kind"), "Software update")))
        if item.get("size"):
            self.details_box.append(self._kv("Download size", item["size"]))
        self.details_box.append(section_title("DESCRIPTION"))
        self.details_box.append(self._paragraph(info.get("description") or "No description available."))
        self.details_box.append(section_title("INFORMATION"))
        for key, label in (("section", "Section"), ("homepage", "Homepage"), ("maintainer", "Maintainer"), ("origin", "Repository")):
            value = info.get(key) or ""
            if value:
                self.details_box.append(self._kv(label, value))
        depends = info.get("depends") or {}
        if depends.get("Depends"):
            self.details_box.append(self._kv("Depends on", ", ".join(depends["Depends"])[:600]))
        self.details_box.append(section_title("PACKAGES AFFECTED"))
        affected = updates.affected_packages(item["package"]) if updates.run else []
        if affected:
            self.details_box.append(self._paragraph(", ".join(affected)[:900]))
        else:
            self.details_box.append(muted_label("No reverse dependencies were reported."))
        self.details_box.append(section_title("CHANGELOG"))
        self.details_box.append(self._paragraph((info.get("changelog") or "").strip() or "No changelog was found for this package."))

    @staticmethod
    def _kv(label, value):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=S(10))
        key = Gtk.Label(label=label); key.add_css_class("muted"); key.set_xalign(0); key.set_width_chars(14)
        val = Gtk.Label(label=value); val.set_xalign(0); val.set_hexpand(True); val.set_wrap(True); val.set_selectable(True)
        box.append(key); box.append(val); return box

    @staticmethod
    def _paragraph(text):
        label = Gtk.Label(label=text); label.set_xalign(0); label.set_wrap(True); label.set_selectable(True)
        label.set_valign(Gtk.Align.START)
        return label
