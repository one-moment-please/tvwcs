"""Hand a network port that Debian's installer set up in /etc/network/interfaces to NetworkManager.

Debian's installer writes the port it installed over into /etc/network/interfaces, run by ifupdown's networking
service ("allow-hotplug wlp2s0", "iface wlp2s0 inet dhcp" and, for Wi-Fi, "wpa-ssid" and "wpa-psk" under it).
NetworkManager's ifupdown plugin, with Debian's default "managed=false", then leaves that port unmanaged, so
Settings could only show it. For Wi-Fi the installer also makes the file readable by root only (it holds the
password), so the whole hand-over runs here, as root:

  1. the port's lines in the interfaces files are turned into comments (a copy is kept as <file>.before-tvwcs);
  2. for Wi-Fi, the network and password (and for either kind, a fixed address) become a NetworkManager connection
     (a keyfile in /etc/NetworkManager/system-connections, readable by root only);
  3. ifupdown lets go of the port, NetworkManager restarts, manages it and connects it;
  4. if NetworkManager cannot connect it, everything is put back as it was and ifupdown brings the port up again,
     so the computer does not end up offline.

Run as `python3 -I ifupdown_handover.py DEVICE`. Only the standard library is used, so it can run as root on its
own; control_network imports the parsing functions from here."""
import ipaddress, os, re, shutil, subprocess, sys, time, uuid

INTERFACES="/etc/network/interfaces"
INTERFACES_D="/etc/network/interfaces.d"
CONNECTIONS="/etc/NetworkManager/system-connections"
TAKEN_NOTE="# Handed to NetworkManager by TVWCS Settings (Network); the copy from before is interfaces.before-tvwcs:"

def ifupdown_lines(text, device):
    """The line numbers (from 0) of the stanza lines for `device`: its auto / allow-* lines, and its iface line with
    the indented options under it. Other interfaces (lo) are not touched."""
    lines=text.splitlines(); found=[]; inside=False
    for i,line in enumerate(lines):
        words=line.split()
        if not words or words[0].startswith("#"):
            continue   # blank lines and comments do not end a stanza's options
        if words[0]=="iface":
            inside=len(words)>1 and words[1]==device
            if inside: found.append(i)
            continue
        if words[0]=="auto" or words[0].startswith("allow-"):
            inside=False
            if device in words[1:]: found.append(i)
            continue
        if words[0] in ("source","source-directory","mapping","no-auto-down","no-scripts","rename"): inside=False; continue
        if inside: found.append(i)
    return found

def without_device(text, device):
    """The interfaces file with `device`'s lines commented out (an auto line naming other interfaces too keeps them)."""
    lines=text.splitlines(); hit=set(ifupdown_lines(text,device)); out=[]; noted=False
    for i,line in enumerate(lines):
        if i not in hit: out.append(line); continue
        if not noted: out.append(TAKEN_NOTE); noted=True
        words=line.split()
        if (words[0]=="auto" or words[0].startswith("allow-")) and len(words)>2:
            out.append("# "+line); out.append(" ".join([words[0]]+[w for w in words[1:] if w!=device]))
        else: out.append("# "+line)
    return "\n".join(out)+("\n" if text.endswith("\n") or not text else "")

def stanza(text, device):
    """`device`'s IPv4 iface stanza as {"method": "dhcp"/"static"/..., option: value}; {} when it has none. An option's
    value is the rest of its line, so a Wi-Fi name with spaces stays whole."""
    lines=text.splitlines(); out={}; current=False
    for i in ifupdown_lines(text,device):
        words=lines[i].split()
        if words[0]=="iface":
            if len(words)>=4 and words[2]=="inet": out["method"]=words[3]
            current=len(words)>=3 and words[2]=="inet"
            continue
        if words[0]=="auto" or words[0].startswith("allow-"): continue
        if out and current:
            parts=lines[i].strip().split(None,1)
            out[parts[0]]=parts[1].strip() if len(parts)>1 else ""
    return out

def wifi_settings(options):
    """(ssid, key management, secret) from a stanza's options: WPA ("wpa-ssid" / "wpa-psk"), WEP or an open network
    ("wireless-essid" / "wireless-key"); None when the stanza names no network (or uses a wpa-conf file instead)."""
    ssid=options.get("wpa-ssid") or options.get("wireless-essid")
    if not ssid: return None
    if ssid.startswith('"') and ssid.endswith('"') and len(ssid)>=2: ssid=ssid[1:-1]
    if options.get("wpa-psk"):
        psk=options["wpa-psk"]
        if psk.startswith('"') and psk.endswith('"') and len(psk)>=2: psk=psk[1:-1]
        return ssid,"wpa-psk",psk
    key=next((options[k] for k in ("wireless-key","wireless-key1") if options.get(k)),"")
    return ssid,("none" if key else ""),key

def static_ipv4(options):
    """(address/prefix, gateway, [dns]) for an "inet static" stanza, else None."""
    if options.get("method")!="static" or not options.get("address"): return None
    address=options["address"].split()[0]
    if "/" not in address:
        try: address=str(ipaddress.IPv4Interface(f"{address}/{options.get('netmask','24').split()[0]}"))
        except ValueError: return None
    try: ipaddress.IPv4Interface(address)
    except ValueError: return None
    return address,options.get("gateway","").split()[0] if options.get("gateway") else "",options.get("dns-nameservers","").split()

def _esc(value):
    """A GKeyFile string value: backslashes, line breaks and a leading space escaped."""
    value=value.replace("\\","\\\\").replace("\n","\\n").replace("\r","\\r").replace("\t","\\t")
    return "\\s"+value[1:] if value.startswith(" ") else value

def keyfile(device, options, kind, ident=None):
    """The NetworkManager keyfile for `device`, from its stanza's options. -> (connection name, uuid, text), or None
    when NetworkManager's own connection does: a wired port on DHCP ("Wired connection 1"), or a Wi-Fi port whose
    network is not in the stanza (it is then chosen in Settings)."""
    ident=ident or str(uuid.uuid4())
    if kind!="wifi" and not static_ipv4(options): return None
    if kind=="wifi":
        wifi=wifi_settings(options)
        if not wifi: return None
        ssid,mgmt,secret=wifi; name=ssid
    else: name=f"Wired ({device})"
    text=["[connection]",f"id={_esc(name)}",f"uuid={ident}","type="+("wifi" if kind=="wifi" else "ethernet"),f"interface-name={device}","autoconnect=true",""]
    if kind=="wifi":
        # the SSID as a list of byte values, which NetworkManager reads whatever characters the name has
        text+=["[wifi]","mode=infrastructure","ssid="+";".join(str(b) for b in ssid.encode())+";",""]
        if mgmt=="wpa-psk": text+=["[wifi-security]","key-mgmt=wpa-psk",f"psk={_esc(secret)}",""]
        elif mgmt=="none": text+=["[wifi-security]","key-mgmt=none","wep-key0="+_esc(secret.removeprefix("s:")),"wep-key-type=1",""]
    else: text+=["[ethernet]",""]
    static=static_ipv4(options)
    if static:
        address,gateway,dns=static
        text+=["[ipv4]","method=manual",f"address1={address}"+(f",{gateway}" if gateway else "")]
        if dns: text.append("dns="+";".join(dns)+";")
        text.append("")
    else: text+=["[ipv4]","method=auto",""]
    text+=["[ipv6]","method=auto",""]
    return name,ident,"\n".join(text)

def interfaces_files():
    files=[INTERFACES]
    try: files+=sorted(os.path.join(INTERFACES_D,n) for n in os.listdir(INTERFACES_D) if not n.startswith("."))
    except OSError: pass
    return files

def device_kind(device):
    return "wifi" if os.path.isdir(f"/sys/class/net/{device}/wireless") or os.path.isdir(f"/sys/class/net/{device}/phy80211") else "ethernet"

def _run(argv, timeout=30):
    try: return subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired) as exc: return subprocess.CompletedProcess(argv,1,"",str(exc))

def _say(line): print(line,flush=True)

def _wait_for_nm():
    for _ in range(15):
        if _run(["nmcli","-t","general"],timeout=5).returncode==0: return
        time.sleep(1)

def _connected(device, timeout=45):
    end=time.time()+timeout
    while time.time()<end:
        out=_run(["nmcli","-t","-g","GENERAL.STATE","device","show",device],timeout=5).stdout
        if out.strip().startswith("100"): return True
        time.sleep(1)
    return False

def hand_over(device):
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+",device): _say("Unexpected device name."); return 2
    kind=device_kind(device); changed=[]; options={}
    for path in interfaces_files():
        try:
            with open(path,encoding="utf-8") as f: text=f.read()
        except OSError: continue
        if not ifupdown_lines(text,device): continue
        options=options or stanza(text,device)
        changed.append((path,text))
    made=keyfile(device,options,kind) if changed else None
    conn_path=""
    if kind=="wifi" and changed and not made:
        _say(f"The Wi-Fi network for {device} is not in the interfaces file, so choose it again in Settings once NetworkManager manages the adapter.")
    for path,text in changed:
        if not os.path.exists(path+".before-tvwcs"): shutil.copy2(path,path+".before-tvwcs")
        mode=os.stat(path).st_mode&0o777
        with open(path,"w",encoding="utf-8") as f: f.write(without_device(text,device))
        os.chmod(path,mode)
    if made:
        name,ident,text=made
        os.makedirs(CONNECTIONS,mode=0o700,exist_ok=True)
        conn_path=os.path.join(CONNECTIONS,"tvwcs-"+re.sub(r"[^A-Za-z0-9_.-]","_",name)[:40]+f"-{ident[:8]}.nmconnection")
        fd=os.open(conn_path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as f: f.write(text)
        _say(f"Saved {name} as a NetworkManager connection.")
    if changed and shutil.which("ifdown"): _run(["ifdown","--force",device])
    if changed: _run(["ip","addr","flush","dev",device])
    _say("Restarting NetworkManager…")
    _run(["systemctl","restart","NetworkManager"]); _wait_for_nm()
    _run(["nmcli","device","set",device,"managed","yes"]); time.sleep(1)
    if made: result=_run(["nmcli","connection","up",made[1]],timeout=60)
    elif kind=="wifi": return 0   # managed now; the network is chosen in Settings
    else: result=_run(["nmcli","device","connect",device],timeout=60)
    if result.returncode==0 or _connected(device,timeout=15): return 0
    _say((result.stderr or result.stdout).strip() or f"NetworkManager could not connect {device}.")
    if not changed: return 1
    # Put it back as it was so the computer stays online
    _say(f"Putting {device} back the way it was…")
    if conn_path:
        try: os.remove(conn_path)
        except OSError: pass
    for path,text in changed:
        mode=os.stat(path).st_mode&0o777
        with open(path,"w",encoding="utf-8") as f: f.write(text)
        os.chmod(path,mode)
    _run(["systemctl","restart","NetworkManager"]); _wait_for_nm()
    if shutil.which("ifup"): _run(["ifup",device],timeout=60)
    return 1

if __name__=="__main__":
    sys.exit(hand_over(sys.argv[1]) if len(sys.argv)==2 else 2)
