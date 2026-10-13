"""Networking backend for the Applications window's Networking tab.

Everything talks to the system through small command-line tools, and every call degrades gracefully:
on a machine without NetworkManager (or `nmcli`) the wifi side simply reports itself unavailable
instead of raising. The pure parsing helpers take raw command output as text so they can be unit
tested without a network stack.

Two backends are supported for editing IPv4 settings:
  * nmcli       — used when a NetworkManager connection exists for the device (the common desktop case)
  * ip + resolv.conf — fallback for plain interfaces (writes /etc/resolv.conf via sudo when needed)
"""
from __future__ import annotations
import ipaddress, re, shlex, shutil, subprocess

# ------------------------------------------------------------------ running commands

def run(argv, timeout=15):
    """Run a command; -> (ok, stdout). Never raises."""
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return out.returncode == 0, out.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return False, ""

def _fields(line):
    return [f.strip() for f in line.split(":")]

def has_tool(name):
    return shutil.which(name) is not None

# ------------------------------------------------------------------ parsing (pure)

IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
MAC_RE = re.compile(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b")

def parse_devices(nmcli_out):
    """`nmcli -t -f DEVICE,TYPE,STATE,CONNECTION devices` -> {ethernet:[...], wifi:[...]}"""
    devices = {"ethernet": [], "wifi": []}
    for line in nmcli_out.splitlines():
        parts = _fields(line)
        if len(parts) < 3:
            continue
        device, dtype, state = parts[0], parts[1].lower(), parts[2]
        connection = parts[3] if len(parts) > 3 else ""
        if not device or dtype not in ("ethernet", "wifi"):
            continue
        devices[dtype].append({"device": device, "state": state, "connection": connection})
    return devices

def parse_address(addresses, wanted):
    """Pick the first IPv4 address of `wanted` from `ip -4 -o addr` lines; -> dict or None."""
    for line in addresses.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1] == wanted:
            cidr = parts[3]
            try:
                net = ipaddress.ip_interface(cidr)
            except ValueError:
                continue
            return {"address": str(net.ip), "prefix": net.network.prefixlen,
                    "cidr": cidr if "/" in cidr else f"{cidr}/32"}
    return None

def parse_routes(routes, wanted):
    """Default gateway on interface `wanted` from `ip -4 -o route` output; -> str or ''."""
    fallback = ""
    for line in routes.splitlines():
        m = re.match(r"default\s+via\s+(\d+\.\d+\.\d+\.\d+)(?:\s+dev\s+(\S+))?", line)
        if not m:
            continue
        if m.group(2) == wanted:
            return m.group(1)
        fallback = fallback or m.group(1)
    return fallback

def parse_resolv(text):
    return IPV4_RE.findall("\n".join(l for l in text.splitlines() if not l.strip().startswith("#")))

def parse_scan(text):
    """`nmcli -t -f SSID,SIGNAL,SECURITY,IN-USE,BARS dev wifi list` -> sorted, de-duplicated networks."""
    seen, nets = {}, []
    for line in text.splitlines():
        parts = line.rstrip().split(":")
        if len(parts) < 4 or not parts[0]:
            continue
        ssid = parts[0]
        try:
            signal = int(re.sub(r"\D", "", parts[1]) or 0)
        except ValueError:
            signal = 0
        entry = {"ssid": ssid, "signal": min(signal, 100), "security": parts[2],
                 "in_use": parts[3].strip() == "*"}
        # Prefer the strongest/bars row for each SSID.
        if ssid not in seen or entry["signal"] > seen[ssid]["signal"]:
            seen[ssid] = entry
    nets = sorted(seen.values(), key=lambda n: (-n["signal"], n["ssid"]))
    return nets

def validate_ipv4(text):
    t = (text or "").strip()
    try:
        ipaddress.IPv4Address(t)
        return True
    except ValueError:
        return False

def validate_cidr(text):
    t = (text or "").strip()
    try:
        ipaddress.IPv4Network(t if "/" in t else t + "/32")
        return True
    except ValueError:
        return False

def dns_list_ok(text):
    items = [t for t in re.split(r"[,\s]+", (text or "").strip()) if t]
    return all(validate_ipv4(i) for i in items)

# ------------------------------------------------------------------ querying

def nm_available():
    ok, _ = run(["nmcli", "-t", "-f", "DEVICE,TYPE", "devices"], timeout=5)
    return ok

def wifi_radio():
    """-> 'enabled' | 'disabled' | 'unknown'"""
    ok, out = run(["rfkill", "list", "wifi"])
    if not ok:
        ok, out = run(["nmcli", "-t", "-f", "RADIO,TYPE", "radio"])
        if not ok:
            return "unknown"
        for line in out.splitlines():
            parts = _fields(line)
            if len(parts) >= 2 and parts[1] == "wlan" and parts[0] in ("enabled", "disabled"):
                return parts[0]
        return "unknown"
    blocked = "yes" in out.lower()
    return "disabled" if blocked else "enabled"

def wifi_enabled():
    _, out = run(["nmcli", "-t", "-f", "WIFI", "general"])
    return out.strip().lower() != "disabled"

def connections_info():
    """Active NM connections: -> {name_or_uuid: {'ipv4.method':..., 'addresses':..., 'gateway':..., 'dns':...}}"""
    info = {}
    ok, out = run(["nmcli", "-t", "-f", "NAME,UUID,TYPE", "connection", "show", "--active"])
    if not ok:
        return info
    for line in out.splitlines():
        parts = _fields(line)
        if len(parts) < 3 or parts[2] not in ("802-3-ethernet", "802-11-wireless"):
            continue
        name, uuid = parts[0], parts[1]
        entry = {"name": name, "uuid": uuid, "type": parts[2], "method": "",
                 "addresses": "", "gateway": "", "dns": ""}
        for setting, key in (("ipv4.method", "method"), ("ipv4.addresses", "addresses"),
                             ("ipv4.gateway", "gateway"), ("ipv4.dns", "dns")):
            _, val = run(["nmcli", "-g", setting, "connection", "show", uuid])
            entry[key] = val.strip()
        info[uuid] = entry
    return info

def scan_wifi():
    """Rescan and return the list of visible networks (may be empty)."""
    run(["nmcli", "-t", "dev", "wifi", "rescan"], timeout=20)
    ok, out = run(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE,BARS", "dev", "wifi", "list", "--rescan", "no"], timeout=20)
    return parse_scan(out) if ok else []

def interface_state(device):
    """Current effective state of an interface: address/gateway/dns/method, from NM where possible."""
    state = {"device": device, "method": "", "address": "", "prefix": "", "gateway": "", "dns": "", "carrier": "", "connection": ""}
    ok, links = run(["ip", "-o", "link", "show", "dev", device])
    if ok:
        state["carrier"] = "UP" if ", UP," in links.upper().replace("LOWER_UP", "") or "state UP" in links else "DOWN"
    _, addrs = run(["ip", "-4", "-o", "addr", "show", "dev", device])
    parsed = parse_address(addrs, device)
    if parsed:
        state["address"] = parsed["address"]; state["prefix"] = str(parsed["prefix"])
    _, routes = run(["ip", "-4", "-o", "route"])
    state["gateway"] = parse_routes(routes, device)
    conns = connections_info()
    conn = None
    _, out = run(["nmcli", "-t", "-f", "NAME,DEVICE,TYPE", "connection", "show", "--active"])
    for line in (out or "").splitlines():
        parts = _fields(line)
        if len(parts) >= 2 and parts[1] == device:
            conn = next((c for c in conns.values() if c["name"] == parts[0]), None)
            state["connection"] = parts[0]
            break
    if conn:
        state["method"] = conn["method"]
        if conn["dns"]:
            state["dns"] = conn["dns"].replace(" ", ", ")
    if not state["dns"]:
        _, res = run(["cat", "/etc/resolv.conf"])
        servers = parse_resolv(res)
        if servers and not _systemd_resolved(servers):
            state["dns"] = ", ".join(servers)
    return state

def _systemd_resolved(servers):
    return any(s.startswith("127.") and s.endswith(("53", "54")) for s in servers)

def connected_ssid():
    _, out = run(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi", "list"])
    for line in out.splitlines():
        parts = line.rstrip().split(":")
        if len(parts) >= 2 and parts[0] == "yes" and parts[1]:
            return parts[1]
    return ""

def ethernet_summary():
    """Quick display rows for the tab: -> (ethernet_devices, wifi_devices)"""
    ok, out = run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "devices"])
    if not ok:
        return [], []
    devices = parse_devices(out)
    return devices["ethernet"], devices["wifi"]

# ------------------------------------------------------------------ changing (pure argv builders)

def set_method_argv(connection, method):
    return ["nmcli", "connection", "modify", connection, "ipv4.method", method]

def set_static_argv(connection, address, prefix, gateway, dns):
    argv = ["nmcli", "connection", "modify", connection,
            "ipv4.method", "manual",
            "ipv4.addresses", f"{address}/{prefix}" if prefix else address,
            "ipv4.gateway", gateway or ""]
    if dns is not None:
        argv += ["ipv4.dns", ",".join(dns)]
    return argv

def connect_wifi_argv(ssid, password=None):
    argv = ["nmcli", "dev", "wifi", "connect", ssid]
    if password:
        argv += ["password", password]
    return argv

def wifi_switch_argv(on):
    return ["nmcli", "radio", "all", "on" if on else "off"]

def reload_connection_argv(uuid):
    return ["nmcli", "connection", "reload"] if not uuid else ["nmcli", "connection", "up", uuid]

def write_resolv_argv(servers):
    """Fallback static DNS: replace the nameserver lines of /etc/resolv.conf through sudo tee."""
    body = "# Written by TVWCS\n" + "".join(f"nameserver {s}\n" for s in servers)
    return ["sudo", "-n", "tee", "/etc/resolv.conf"], body

def apply_dns_fallback(servers):
    argv, body = write_resolv_argv(servers)
    try:
        proc = subprocess.run(argv, input=body, text=True, capture_output=True, timeout=15)
        return proc.returncode == 0, (proc.stderr or "").strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)

def apply_ip_fallback(device, address, prefix):
    ok, _ = run(["sudo", "-n", "ip", "addr", "flush", "dev", device, "scope", "global"])
    if not ok:
        return False, "Could not clear the interface's addresses (sudo is required)."
    return run(["sudo", "-n", "ip", "addr", "add", f"{address}/{prefix or 24}", "dev", device])

def apply_gateway_fallback(gateway):
    run(["sudo", "-n", "ip", "route", "del", "default"])   # best effort
    return run(["sudo", "-n", "ip", "route", "add", "default", "via", gateway])

def parse_static_form(address_text, gateway_text, dns_text):
    """Validate the Networking tab's static form. -> (errors, (address, prefix, gateway, [dns]))"""
    errors = []
    address, prefix = "", ""
    text = (address_text or "").strip()
    if not text:
        errors.append("An IP address is required.")
    elif "/" in text:
        if not validate_cidr(text):
            errors.append("The IP address/CIDR is not valid (for example 192.168.1.20/24).")
        else:
            address, prefix = text.split("/", 1)
    elif validate_ipv4(text):
        address = text; prefix = "24"
    else:
        errors.append("The IP address is not valid (for example 192.168.1.20).")
    gateway = (gateway_text or "").strip()
    if gateway and not validate_ipv4(gateway):
        errors.append("The default gateway is not a valid IPv4 address.")
    dns_items = [t for t in re.split(r"[,\s]+", (dns_text or "").strip()) if t]
    if not dns_list_ok(",".join(dns_items)):
        bad = next((d for d in dns_items if not validate_ipv4(d)), "")
        errors.append(f"The DNS server “{bad}” is not a valid IPv4 address." if bad else "DNS servers are invalid.")
    return errors, (address, prefix, gateway, dns_items)

def shell_command_ok(command):
    """True when a free-text command line parses to at least one argument."""
    try:
        return bool(shlex.split(command or ""))
    except ValueError:
        return False
