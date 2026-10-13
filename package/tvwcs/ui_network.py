"""The Networking tab of the Applications window.

Shows ethernet and wifi interfaces with their IP addresses, the connected wifi network, and lets the
user edit IPv4 settings (DHCP or manual address / gateway / DNS), scan for and connect to wifi
networks, or switch wifi off. Everything goes through tvwcs.network so it degrades gracefully when
NetworkManager is missing; long commands run in a background thread so the UI never freezes.
"""
from __future__ import annotations
import threading
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

from tvwcs import network
from tvwcs.widgets import NavGroup, S, clear_box, glyph, icon_button, muted_label, section_title, usable


def _signal_bars(signal):
    """0-100 -> ▁▃▅▇ style bars."""
    if signal >= 75: return "▂▄▆█"
    if signal >= 50: return "▂▄▆_"
    if signal >= 25: return "▂▄__"
    return "▂___"


class NetworkingTab(Gtk.Box):
    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=S(4))
        self.win = win
        self.app = win.app
        self._busy = False
        self._scan_results = []
        self._wifi_on = True
        self.add_css_class("pane")
        self.set_margin_start(S(24)); self.set_margin_end(S(24)); self.set_margin_bottom(S(16))
        self.reload()

    # ------------------------------------------------------------- helpers
    def register(self, *widgets):
        group = NavGroup([w for w in widgets if w is not None])
        if group:
            self.win._groups["guide"].append(group)

    def _async(self, work, done):
        """Run `work()` off the UI thread; call done(result) on it when finished."""
        def runner():
            result = work()
            GLib.idle_add(lambda: self._finish(done, result))
        self._set_busy(True)
        threading.Thread(target=runner, daemon=True).start()

    def _finish(self, done, result):
        self._set_busy(False)
        done(result)

    def _set_busy(self, busy):
        self._busy = busy
        if hasattr(self, "status"):
            self.status.set_visible(busy)
        if hasattr(self, "spinner"):
            (self.spinner.start if busy else self.spinner.stop)()

    def message(self, text):
        if hasattr(self, "banner"):
            self.banner.set_text(text)
            self.banner.set_visible(bool(text))

    # ------------------------------------------------------------- build
    def reload(self):
        """Rebuild the tab's content. The parent (Applications pane) clears this box and its nav groups
        before calling it, so only fresh widgets are added."""
        if self._busy:
            return
        self.message("")
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=S(10))
        header.set_margin_top(S(6)); header.set_margin_bottom(S(6))
        refresh = Gtk.Button(label="Refresh"); refresh.connect("clicked", lambda *_: self.win.refresh_applications_tab("network"))
        header.append(refresh); self.register(refresh)
        self.spinner = Gtk.Spinner(); self.status = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=S(8)); self.status.set_visible(False)
        self.status.append(self.spinner); self.status.append(muted_label("Working…")); header.append(self.status)
        self.append(header)
        self.banner = muted_label(""); self.banner.add_css_class("error"); self.banner.set_visible(False)
        self.append(self.banner)
        self._build_ethernet()
        self._build_wifi()

    def _row_card(self, title_lines, detail_pairs, buttons=()):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=S(4))
        card.add_css_class("net-card"); card.set_margin_top(S(4)); card.set_margin_bottom(S(4))
        card.set_margin_start(S(8)); card.set_margin_end(S(8)); card.set_padding(S(10))
        for line in title_lines:
            t = Gtk.Label(label=line); t.set_xalign(0); t.add_css_class("net-title"); card.append(t)
        grid = Gtk.Grid(); grid.set_column_spacing(S(14)); grid.set_row_spacing(S(2))
        for i, (key, value) in enumerate(detail_pairs):
            k = Gtk.Label(label=key); k.add_css_class("muted"); k.set_xalign(0)
            v = Gtk.Label(label=value or "—"); v.set_xalign(0); v.set_hexpand(True); v.set_selectable(True)
            grid.attach(k, 0, i, 1, 1); grid.attach(v, 1, i, 1, 1)
        card.append(grid)
        if buttons:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=S(6)); row.set_margin_top(S(6))
            for b in buttons:
                row.append(b)
            card.append(row); self.register(*buttons)
        return card

    def _build_ethernet(self):
        self.append(section_title("ETHERNET"))
        eth, _ = ([], [])
        if network.nm_available():
            eth, _ = network.ethernet_summary()
        if not eth:
            self.append(muted_label("No wired interfaces were reported by NetworkManager."))
            return
        for device in eth:
            name = device["device"]
            state = network.interface_state(name)
            ip = f"{state['address']}/{state['prefix']}" if state["address"] else "—"
            buttons = []
            edit = Gtk.Button(label="Edit IP settings")
            edit.connect("clicked", lambda _b, d=name: self._edit_ip(d))
            buttons.append(edit)
            card = self._row_card(
                [f"{name}  ·  {device['state']}" + (f"  ·  {device['connection']}" if device["connection"] else "")],
                [("IP address", ip), ("Default gateway", state["gateway"]),
                 ("DNS servers", state["dns"]),
                 ("Method", "DHCP" if state["method"] == "auto" else ("Manual" if state["method"] == "manual" or state["method"] else ""))],
                buttons)
            self.append(card)

    def _build_wifi(self):
        self.append(section_title("WIFI"))
        if not network.nm_available():
            self.append(muted_label("NetworkManager (nmcli) was not found, so wifi cannot be managed from here."))
            return
        self._wifi_on = network.wifi_enabled()
        toggle = Gtk.ToggleButton(label="Wi-Fi on" if self._wifi_on else "Wi-Fi off")
        toggle.set_active(self._wifi_on)
        toggle.connect("toggled", self._wifi_toggled)
        scan = Gtk.Button(label="Scan for networks")
        scan.connect("clicked", lambda *_: self._scan())
        self.append(self._row_card(["Status"], [("Radio", "enabled" if self._wifi_on else "disabled"),
                                                        ("Connected network", network.connected_ssid() or "not connected")],
                                           [toggle, scan]))
        self.register(toggle, scan)
        self.scan_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=S(2))
        self.append(self.scan_box)
        if self._scan_results:
            self._show_scan(self._scan_results)
        elif self._wifi_on:
            self.scan_box.append(muted_label("Press “Scan for networks” to list the access points around you."))

    # ------------------------------------------------------------- actions
    def _wifi_toggled(self, button):
        want_on = button.get_active()
        self.message("")
        self._async(lambda: network.run(network.wifi_switch_argv(want_on)),
                    lambda res: (self.reload(),
                                 self.message("" if res[0] else f"Could not change the wifi radio: {res[1] or 'nmcli failed'}")))

    def _scan(self):
        self.message("")
        def done(results):
            self._scan_results = results
            self._show_scan(results)
        self._async(network.scan_wifi, done)

    def _show_scan(self, results):
        clear_box(self.scan_box)
        if not results:
            self.scan_box.append(muted_label("No networks found. Is the wifi radio on?"))
            return
        self.scan_box.append(section_title("NETWORKS"))
        for net in results[:20]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=S(10))
            name = Gtk.Label(label=("* " if net["in_use"] else "") + net["ssid"])
            name.set_xalign(0); name.set_hexpand(True); name.set_ellipsize(3)
            row.append(name)
            strength = Gtk.Label(label=f"{_signal_bars(net['signal'])} {net['signal']}%"); strength.add_css_class("muted")
            row.append(strength)
            secured = bool(net["security"] and "open" not in net["security"].lower())
            connect = Gtk.Button(label="Connect" if not net["in_use"] else "Connected")
            connect.set_sensitive(not net["in_use"])
            connect.connect("clicked", lambda _b, n=net, anchor=connect: self._connect(n, anchor))
            row.append(connect)
            self.scan_box.append(row)
            self.register(connect)
            if secured and not net["in_use"]:
                hint = muted_label("🔒 " + net["security"]); self.scan_box.append(hint)

    def _connect(self, net, anchor):
        open_network = not (net["security"] and "open" not in net["security"].lower())
        if open_network:
            self._do_connect(net["ssid"], None)
            return
        self.win.ask_wifi_password(net["ssid"], lambda password: self._do_connect(net["ssid"], password))

    def _do_connect(self, ssid, password):
        self.message(f"Connecting to {ssid}…")
        def done(res):
            ok, out = res
            self.message("" if ok else f"Could not connect to {ssid}: {(out or 'nmcli failed').strip()[:200]}")
            self.reload()
        self._async(lambda: network.run(network.connect_wifi_argv(ssid, password), timeout=30), done)

    # ------------------------------------------------------------- IP editor (modal inside the tab)
    def _edit_ip(self, device):
        win = self.win
        state = network.interface_state(device)
        win._begin_modal()
        win._title(f"IP settings · {device}")
        card = win.modal_card
        method_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=S(6)); method_row.set_homogeneous(True)
        dhcp = Gtk.ToggleButton(label="DHCP"); manual = Gtk.ToggleButton(label="Manual")
        groups = []
        address = Gtk.Entry(); address.set_hexpand(True)
        address.set_text(f"{state['address']}/{state['prefix']}" if state["address"] else "")
        address.set_placeholder_text("e.g. 192.168.1.20/24")
        gateway = Gtk.Entry(); gateway.set_text(state["gateway"]); gateway.set_placeholder_text("e.g. 192.168.1.1")
        dns = Gtk.Entry(); dns.set_text(state["dns"]); dns.set_placeholder_text("e.g. 1.1.1.1, 8.8.8.8")
        fields = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=S(6)); fields.set_visible(False)
        for label, widget in (("IP address / CIDR", address), ("Default gateway", gateway), ("DNS servers", dns)):
            wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=S(2))
            lab = Gtk.Label(label=label); lab.set_xalign(0); lab.add_css_class("muted"); wrap.append(lab); wrap.append(widget)
            fields.append(wrap)
        error = Gtk.Label(label=""); error.set_xalign(0); error.set_wrap(True); error.add_css_class("error"); card.append(error)

        def pick(use_manual):
            dhcp.set_active(use_manual is False); manual.set_active(use_manual)
            fields.set_visible(use_manual)
        dhcp.connect("toggled", lambda b: pick(False) if b.get_active() else None)
        manual.connect("toggled", lambda b: pick(True) if b.get_active() else None)
        if state["method"] != "auto":
            pick(True)
        else:
            pick(False)
        method_row.append(dhcp); method_row.append(manual)
        card.append(method_row); card.append(fields)
        save = Gtk.Button(label="Apply"); save.add_css_class("active")
        cancel = Gtk.Button(label="Close")
        cancel.connect("clicked", lambda *_: win.close_modal())
        save.connect("clicked", lambda *_: self._apply_ip(device, state, manual.get_active(), address, gateway, dns, error))
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=S(6)); buttons.set_homogeneous(True); buttons.set_margin_top(S(8))
        buttons.append(cancel); buttons.append(save); card.append(buttons)
        win._modal_groups = [NavGroup([dhcp, manual]), NavGroup([address]), NavGroup([gateway]), NavGroup([dns]), NavGroup([cancel, save])]
        win._modal_back = win.close_modal
        (address if manual.get_active() else dhcp).grab_focus()

    def _apply_ip(self, device, state, use_manual, address, gateway, dns, error):
        if not use_manual:
            def done(res):
                ok, out = res
                if ok:
                    self.win.close_modal(); self.reload(); self.message("DHCP enabled.")
                else:
                    error.set_text(f"Could not switch to DHCP: {(out or 'nmcli failed').strip()[:200]}")
            connection = state.get("connection") or device
            self._async(lambda: (network.run(network.set_method_argv(connection, "auto")),
                                 network.run(network.reload_connection_argv(None)))[0], done)
            return
        errors, (ip, prefix, gw, servers) = network.parse_static_form(address.get_text(), gateway.get_text(), dns.get_text())
        if errors:
            error.set_text("  ".join(errors)); return
        connection = state.get("connection")
        def done(res):
            ok, out = res
            if ok:
                self.win.close_modal(); self.reload(); self.message(f"Static IP {ip} applied to {device}.")
            else:
                error.set_text((out or "Applying the settings failed.").strip()[:300])
        if connection:
            argv = network.set_static_argv(connection, ip, prefix, gw, servers)
            self._async(lambda: (network.run(argv), network.run(network.reload_connection_argv(connection)))[0], done)
        else:
            def fallback():
                ok_a, out_a = network.apply_ip_fallback(device, ip, prefix)
                if not ok_a:
                    return False, out_a
                if gw:
                    ok_g, out_g = network.apply_gateway_fallback(gw)
                    if not ok_g:
                        return False, out_g
                if servers:
                    ok_d, out_d = network.apply_dns_fallback(servers)
                    if not ok_d:
                        return False, out_d
                return True, ""
            self._async(fallback, done)
