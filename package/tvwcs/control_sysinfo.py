"""System information for the Control Panel, read from /proc, /sys and a few commands. No GTK dependency.
Each reader takes its text as an argument, so it can be tested with saved files."""
from __future__ import annotations
import glob, os, platform, re, shutil, socket
from pathlib import Path

from tvwcs import __version__
from tvwcs.control_cmd import have, run

def _read(path):
    try: return Path(path).read_text(encoding="utf-8",errors="replace")
    except OSError: return ""

def parse_os_release(text):
    """/etc/os-release -> its PRETTY_NAME (or NAME VERSION)."""
    values={}
    for line in text.splitlines():
        key,found,value=line.partition("=")
        if found: values[key.strip()]=value.strip().strip('"').strip("'")
    return values.get("PRETTY_NAME") or " ".join(v for v in (values.get("NAME"),values.get("VERSION")) if v)

def parse_cpu(text):
    """/proc/cpuinfo -> the processor's name. ARM boards often name the board instead (Model: Raspberry Pi 4 …)."""
    fields={}
    for line in text.splitlines():
        key,found,value=line.partition(":")
        if found and value.strip(): fields.setdefault(key.strip().lower(),value.strip())
    board=fields.get("model","")   # a Raspberry Pi's board; on x86 "model" is only a number
    name=fields.get("model name") or (board if board and not board.isdigit() else "") or fields.get("hardware") or fields.get("cpu model") or ""
    return re.sub(r"\s+"," ",re.sub(r"\((R|TM)\)","",name,flags=re.I)).strip()

def parse_meminfo(text):
    """/proc/meminfo -> (total, available) in bytes."""
    values={}
    for line in text.splitlines():
        m=re.match(r"^(\w+):\s+(\d+)\s*kB",line)
        if m: values[m.group(1)]=int(m.group(2))*1024
    total=values.get("MemTotal",0)
    return total,values.get("MemAvailable",values.get("MemFree",0))

def size_text(n):
    """Bytes -> '7.6 GB' (decimal units, as disks are sold)."""
    for unit,size in (("TB",1e12),("GB",1e9),("MB",1e6),("kB",1e3)):
        if n>=size: return f"{n/size:.1f} {unit}"
    return f"{int(n)} B"

def duration_text(seconds):
    """Seconds -> '3 days, 4 hours' / '2 hours, 5 minutes' / '12 minutes'."""
    seconds=int(seconds); days,rest=divmod(seconds,86400); hours,rest=divmod(rest,3600); minutes=rest//60
    def part(n,unit): return f"{n} {unit}{'s' if n!=1 else ''}"
    if days: return part(days,"day")+(", "+part(hours,"hour") if hours else "")
    if hours: return part(hours,"hour")+(", "+part(minutes,"minute") if minutes else "")
    return part(minutes,"minute")

def parse_lspci_gpus(text):
    """`lspci` -> the display adapters, without their bus address and class."""
    gpus=[]
    for line in text.splitlines():
        m=re.match(r"^\S+\s+(?:VGA compatible controller|3D controller|Display controller):\s*(.*)$",line)
        if m: gpus.append(re.sub(r"\s*\(rev \w+\)$","",m.group(1)).strip())
    return gpus

def window_manager(env=None):
    """'i3 4.23', 'sway 1.9', or what XDG_CURRENT_DESKTOP says."""
    env=os.environ if env is None else env
    for tool,marker in (("sway","SWAYSOCK"),("i3","I3SOCK")):
        if env.get(marker) or (tool=="i3" and env.get("DESKTOP_SESSION","").startswith("i3")) or (tool=="sway" and env.get("XDG_CURRENT_DESKTOP","").lower()=="sway"):
            if have(tool):
                m=re.search(r"version\s+(\S+)",run([tool,"--version"],timeout=5).out)
                if m: return f"{tool} {m.group(1).rstrip(',')}"
            return tool
    return env.get("XDG_CURRENT_DESKTOP") or env.get("DESKTOP_SESSION") or ""

def battery(root="/sys/class/power_supply"):
    """'85 %, charging' for the first battery, or ''."""
    for path in sorted(glob.glob(f"{root}/BAT*")):
        capacity=_read(f"{path}/capacity").strip(); status=_read(f"{path}/status").strip()
        if capacity: return f"{capacity} %"+(f", {status.lower()}" if status and status!="Unknown" else "")
    return ""

def cpu_temperature(root="/sys/class/thermal"):
    """The processor's temperature ('48 °C'), preferring the package sensor, or ''."""
    best=None
    for zone in sorted(glob.glob(f"{root}/thermal_zone*")):
        kind=_read(f"{zone}/type").strip(); raw=_read(f"{zone}/temp").strip()
        if not raw.lstrip("-").isdigit(): continue
        rank=0 if kind in ("x86_pkg_temp","cpu-thermal","cpu_thermal","k10temp","coretemp") else 1
        if best is None or rank<best[0]: best=(rank,int(raw)/1000)
    return f"{best[1]:.0f} °C" if best else ""

def gtk_version():
    try:
        import gi
        gi.require_version("Gtk","4.0")
        from gi.repository import Gtk
        return f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}"
    except (ImportError,ValueError,AttributeError): return ""

def read_sections():
    """[(section title, [(label, value)])], every value already formatted. Empty values are left out."""
    total,free=parse_meminfo(_read("/proc/meminfo"))
    try: uptime=duration_text(float(_read("/proc/uptime").split()[0]))
    except (IndexError,ValueError): uptime=""
    cpus=os.cpu_count() or 0
    session=os.environ.get("XDG_SESSION_TYPE",""); session={"x11":"X11","wayland":"Wayland"}.get(session.lower(),session)
    cpu=parse_cpu(_read("/proc/cpuinfo"))
    gpus=parse_lspci_gpus(run(["lspci"],timeout=5).out) if have("lspci") else []
    disks=[]
    for label,path in (("System disk","/"),("Home",str(Path.home()))):
        try: u=shutil.disk_usage(path)
        except OSError: continue
        if label=="Home" and os.stat(path).st_dev==os.stat("/").st_dev: continue   # the same disk as /
        disks.append((label,f"{size_text(u.free)} free of {size_text(u.total)}"))
    sections=[
        ("THIS COMPUTER",[("Name",socket.gethostname()),
                          ("Operating system",parse_os_release(_read("/etc/os-release") or _read("/usr/lib/os-release"))),
                          ("Kernel",f"Linux {platform.release()} ({platform.machine()})"),
                          ("Up for",uptime),
                          ("Window manager",window_manager()),
                          ("Session",session)]),
        ("HARDWARE",[("Processor",f"{cpu} ({cpus} threads)" if cpu and cpus else cpu or (f"{cpus} threads" if cpus else "")),
                     ("Processor temperature",cpu_temperature()),
                     ("Memory",f"{size_text(free)} free of {size_text(total)}" if total else ""),
                     *[("Graphics" if i==0 else "",g) for i,g in enumerate(gpus)],
                     ("Battery",battery())]),
        ("STORAGE",disks),
        ("SOFTWARE",[("TVWCS",__version__),("Python",platform.python_version()),("GTK",gtk_version())]),
    ]
    return [(title,[(k,v) for k,v in rows if v]) for title,rows in sections if any(v for _k,v in rows)]
