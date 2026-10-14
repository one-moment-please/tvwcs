"""Ethernet and Wi-Fi for the Control Panel. No GTK dependency.

Changes go through NetworkManager's `nmcli`, which polkit lets the user at the screen use without a password.
Without NetworkManager the panel still shows every interface, its addresses and the gateway (from `ip`), read-only."""
from __future__ import annotations
import ipaddress, json, os, re
from dataclasses import dataclass, field

from tvwcs.control_cmd import have, run, split_terse

@dataclass
class Interface:
    device: str
    kind: str                 # "ethernet" or "wifi"
    state: str = ""           # connected, disconnected, unavailable (no cable), connecting, ...
    connection: str = ""      # the active NetworkManager connection's name
    connection_uuid: str = ""
    mac: str = ""
    addresses: list = field(default_factory=list)   # "192.168.1.20/24"
    gateway: str = ""
    dns: list = field(default_factory=list)
    method: str = ""          # the connection's IPv4 method: "auto" (DHCP) or "manual"; "" when there is no connection
    @property
    def connected(self): return self.state.startswith("connected")

@dataclass
class WifiNetwork:
    ssid: str
    signal: int
    security: str
    in_use: bool = False
    saved_uuid: str = ""     # a saved connection for it ("" = none)
    @property
    def secured(self): return bool(self.security.strip()) and self.security.strip()!="--"

@dataclass
class NetState:
    managed: bool                 # NetworkManager is there to change things
    message: str = ""
    interfaces: list = field(default_factory=list)
    wifi_enabled: bool = False
    networks: list = field(default_factory=list)
    def of_kind(self, kind): return [i for i in self.interfaces if i.kind==kind]

@dataclass
class Ipv4Settings:
    method: str = "auto"          # "auto" (DHCP) or "manual"
    address: str = ""             # "192.168.1.20/24"
    gateway: str = ""
    dns: str = ""                 # comma separated
    @property
    def automatic(self): return self.method!="manual"

# ------------------------------------------------------------------ parsing (pure)
_STATE=re.compile(r"^\d+\s*\((.*)\)$")

def parse_device_list(text):
    """`nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device` -> [Interface] (Ethernet and Wi-Fi only)."""
    found=[]
    for line in text.splitlines():
        f=split_terse(line)
        if len(f)>=3 and f[1] in ("ethernet","wifi"):
            found.append(Interface(f[0],f[1],f[2],f[3] if len(f)>3 and f[3]!="--" else ""))
    return found

def parse_device_show(text, iface):
    """`nmcli -t -f GENERAL.HWADDR,GENERAL.STATE,GENERAL.CONNECTION,IP4 device show <dev>` into `iface`."""
    for line in text.splitlines():
        key,value=(split_terse(line,1)+[""])[:2]
        key=key.split("[")[0]
        if not value or value=="--": continue
        if key=="GENERAL.HWADDR": iface.mac=value
        elif key=="GENERAL.STATE":
            m=_STATE.match(value); iface.state=m.group(1) if m else value
        elif key=="IP4.ADDRESS": iface.addresses.append(value)
        elif key=="IP4.GATEWAY": iface.gateway=value
        elif key=="IP4.DNS": iface.dns.append(value)
    return iface

def parse_connections(text):
    """`nmcli -t -f NAME,UUID,TYPE,DEVICE connection show` -> [(name, uuid, type, device)]."""
    rows=[]
    for line in text.splitlines():
        f=split_terse(line)
        if len(f)>=4: rows.append((f[0],f[1],f[2],"" if f[3]=="--" else f[3]))
    return rows

def parse_wifi_list(text):
    """`nmcli -t -f IN-USE,SSID,SIGNAL,SECURITY device wifi list` -> [WifiNetwork], one per name, strongest first.
    Hidden networks (no name) are left out."""
    best={}
    for line in text.splitlines():
        f=split_terse(line)
        if len(f)<4 or not f[1]: continue
        try: signal=max(0,min(100,int(f[2] or 0)))
        except ValueError: signal=0
        net=WifiNetwork(f[1],signal,f[3],f[0].strip()=="*")
        old=best.get(net.ssid)
        if old is None or (net.in_use and not old.in_use) or (net.in_use==old.in_use and signal>old.signal): best[net.ssid]=net
    return sorted(best.values(),key=lambda n:(not n.in_use,-n.signal,n.ssid.casefold()))

def _physical(name): return os.path.exists(f"/sys/class/net/{name}/device")

def parse_ip_json(addr_json, route_json, physical=_physical):
    """`ip -j addr` and `ip -j route` -> [Interface], for systems without NetworkManager. Loopback and virtual
    interfaces (bridges, containers, tunnels) are left out."""
    try: links=json.loads(addr_json or "[]")
    except ValueError: links=[]
    try: routes=json.loads(route_json or "[]")
    except ValueError: routes=[]
    gateways={r.get("dev"):r.get("gateway","") for r in routes if r.get("dst")=="default" and r.get("gateway")}
    found=[]
    for link in links:
        name=link.get("ifname","")
        if not name or not physical(name): continue
        if link.get("link_type") not in (None,"ether"): continue   # loopback, tunnels, …
        kind="wifi" if os.path.isdir(f"/sys/class/net/{name}/wireless") else "ethernet"
        up="UP" in link.get("flags",[]) and "LOWER_UP" in link.get("flags",[])
        addresses=[f"{a['local']}/{a.get('prefixlen',32)}" for a in link.get("addr_info",[]) if a.get("family")=="inet" and a.get("local")]
        found.append(Interface(name,kind,"connected" if up and addresses else "disconnected" if up else "unavailable","",
                               "",link.get("address",""),addresses,gateways.get(name,"")))
    return found

def parse_ipv4(text):
    """`nmcli -t -f ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns connection show <uuid>` -> Ipv4Settings."""
    s=Ipv4Settings()
    for line in text.splitlines():
        key,value=(split_terse(line,1)+[""])[:2]
        value="" if value=="--" else value
        if key=="ipv4.method": s.method="manual" if value=="manual" else "auto"
        elif key=="ipv4.addresses": s.address=value.split(",")[0].strip()
        elif key=="ipv4.gateway": s.gateway=value
        elif key=="ipv4.dns": s.dns=value
    return s

def signal_bars(signal):
    """0-100 -> a four-step bar glyph, for the Wi-Fi list."""
    return "▂▄▆█"[:max(1,min(4,(signal+24)//25))]

def validate_ipv4(settings):
    """-> (problem or "", nmcli arguments for `connection modify`)."""
    if settings.automatic:
        return "",["ipv4.method","auto","ipv4.addresses","","ipv4.gateway","","ipv4.dns",""]
    text=settings.address.strip()
    try: iface=ipaddress.IPv4Interface(text if "/" in text else text+"/24")
    except ValueError: return f"“{text or 'nothing'}” is not an IPv4 address (for example 192.168.1.20/24).",[]
    gateway=settings.gateway.strip()
    if gateway:
        try:
            if ipaddress.IPv4Address(gateway) not in iface.network: return f"The gateway {gateway} is not on the network {iface.network}.",[]
        except ValueError: return f"“{gateway}” is not an IPv4 address.",[]
    servers=[s for s in re.split(r"[,\s]+",settings.dns.strip()) if s]
    for s in servers:
        try: ipaddress.ip_address(s)
        except ValueError: return f"The DNS server “{s}” is not an IP address.",[]
    return "",["ipv4.method","manual","ipv4.addresses",iface.with_prefixlen,"ipv4.gateway",gateway,"ipv4.dns",",".join(servers)]

def fixed_from(settings, iface):
    """Switching from DHCP to a fixed address: start from the address, gateway and DNS servers in use now."""
    out=Ipv4Settings("manual",settings.address,settings.gateway,settings.dns)
    if not out.address and iface is not None and iface.addresses: out.address=iface.addresses[0]
    if not out.gateway and iface is not None: out.gateway=iface.gateway
    if not out.dns and iface is not None: out.dns=", ".join(iface.dns)
    return out

# ------------------------------------------------------------------ reading
def read_state(scan=False):
    if not have("nmcli") or not run(["nmcli","-t","-f","RUNNING","general"],timeout=5).out.strip()=="running":
        addr=run(["ip","-j","addr"],timeout=5); route=run(["ip","-j","route"],timeout=5)
        why=("NetworkManager is not running, so these settings can only be shown here. Start NetworkManager to change them."
             if have("nmcli") else "Changing these settings needs NetworkManager (nmcli). Without it they can only be shown here.")
        return NetState(False,why,parse_ip_json(addr.out,route.out))
    interfaces=parse_device_list(run(["nmcli","-t","-f","DEVICE,TYPE,STATE,CONNECTION","device"],timeout=8).out)
    connections=parse_connections(run(["nmcli","-t","-f","NAME,UUID,TYPE,DEVICE","connection","show"],timeout=8).out)
    for iface in interfaces:
        parse_device_show(run(["nmcli","-t","-f","GENERAL.HWADDR,GENERAL.STATE,IP4","device","show",iface.device],timeout=8).out,iface)
        iface.connection_uuid=next((u for _n,u,_t,d in connections if d==iface.device),"")
        if iface.connection_uuid:
            method=run(["nmcli","-g","ipv4.method","connection","show",iface.connection_uuid],timeout=5).out.strip()
            iface.method="manual" if method=="manual" else "auto"
    wifi_on=run(["nmcli","-t","radio","wifi"],timeout=5).out.strip()=="enabled"
    networks=[]
    if wifi_on and any(i.kind=="wifi" for i in interfaces):
        # only a search asks the adapter to scan; otherwise this lists what NetworkManager already knows
        listing=run(["nmcli","-t","-f","IN-USE,SSID,SIGNAL,SECURITY","device","wifi","list","--rescan","yes" if scan else "no"],timeout=30)
        networks=parse_wifi_list(listing.out)
        saved=saved_wifi(connections)
        for n in networks: n.saved_uuid=saved.get(n.ssid,"")
    return NetState(True,"",interfaces,wifi_on,networks)

def saved_wifi(connections):
    """{ssid: uuid} of the saved Wi-Fi connections (a connection's name is not always its network's name)."""
    found={}
    for name,uuid,kind,_dev in connections:
        if kind not in ("802-11-wireless","wifi"): continue
        ssid=run(["nmcli","-g","802-11-wireless.ssid","connection","show",uuid],timeout=5).out.strip() or name
        found.setdefault(ssid,uuid)
    return found

def read_ipv4(uuid):
    return parse_ipv4(run(["nmcli","-t","-f","ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns","connection","show",uuid],timeout=8).out)

# ------------------------------------------------------------------ changing (each -> "" on success, else why not)
def _outcome(result):
    if result.ok: return ""
    m=re.search(r"Error: (.*)",result.err or result.out)
    reason=m.group(1).strip() if m else result.message
    if "Secrets were required" in reason or "802-1x" in reason: return "The password was not accepted."
    if "Not authorized" in reason or "not authorized" in reason: return "NetworkManager did not allow this user to change that (polkit)."
    return reason

def set_wifi(on): return _outcome(run(["nmcli","radio","wifi","on" if on else "off"],timeout=10))
def connect_device(device): return _outcome(run(["nmcli","device","connect",device],timeout=45))
def disconnect_device(device): return _outcome(run(["nmcli","device","disconnect",device],timeout=20))
def activate(uuid): return _outcome(run(["nmcli","connection","up",uuid],timeout=45))
def forget(uuid): return _outcome(run(["nmcli","connection","delete",uuid],timeout=15))

def join_wifi(ssid, password=None):
    """Join a network not saved yet. A failed attempt leaves no half-made connection behind to fail again next time.
    The password is passed as an argument, as `nmcli device wifi connect` documents."""
    before={u for _n,u,_t,_d in parse_connections(run(["nmcli","-t","-f","NAME,UUID,TYPE,DEVICE","connection","show"],timeout=8).out)}
    argv=["nmcli","device","wifi","connect",ssid]+(["password",password] if password else [])
    problem=_outcome(run(argv,timeout=60))
    if problem:
        for _n,u,_t,_d in parse_connections(run(["nmcli","-t","-f","NAME,UUID,TYPE,DEVICE","connection","show"],timeout=8).out):
            if u not in before: run(["nmcli","connection","delete",u],timeout=15)
    return problem

def apply_ipv4(uuid, settings):
    """Save the IPv4 settings on a connection and re-activate it so they take effect."""
    problem,args=validate_ipv4(settings)
    if problem: return problem
    problem=_outcome(run(["nmcli","connection","modify",uuid,*args],timeout=15))
    return problem or activate(uuid)
