"""Date and time for Settings: the time zone (picked as a region, then a city), whether the clock is set from the
network (NTP), and the clock shown at the bottom of the Quick Menu. No GTK dependency.

systemd's timedatectl reads and changes these. polkit usually wants a password for changes, and i3 and sway run no
polkit agent to ask for it, so the panel runs the same command as root when polkit refuses. Without timedatectl the
time zone is read from the /etc/localtime link and set by pointing that link at another zone (as root)."""
from __future__ import annotations
import datetime, os, time
from dataclasses import dataclass, field
from pathlib import Path

from tvwcs.control_cmd import have, key_values, run

ZONEINFO=Path("/usr/share/zoneinfo")
LOCALTIME=Path("/etc/localtime")
# Folders of /usr/share/zoneinfo that hold copies, aliases or data files rather than places to choose.
_NOT_REGIONS={"posix","right","Etc","SystemV","US","Brazil","Canada","Chile","Mexico"}
OTHER="Other"   # the region of zones without one (UTC)

@dataclass
class TimeState:
    timezone: str=""
    ntp: bool=False             # the clock is set from the network
    synced: bool=False          # ... and it has been set
    can_ntp: bool=False         # a network time service is installed (systemd-timesyncd, chrony, ntpd)
    timedatectl: bool=False     # changes go through timedatectl; otherwise only the time zone can be changed
    zones: list=field(default_factory=list)

# ---------------------------------------------------------------------- reading
def parse_show(text):
    """`timedatectl show` -> (time zone, NTP on, synchronised, can NTP)."""
    v=key_values(text,sep="=")
    yes=lambda k:v.get(k,"").strip().lower()=="yes"
    return v.get("Timezone","").strip(),yes("NTP"),yes("NTPSynchronized"),yes("CanNTP")

def zone_from_link(target):
    """'/usr/share/zoneinfo/Europe/Paris' (or '../usr/share/zoneinfo/...') -> 'Europe/Paris'."""
    marker="zoneinfo/"
    return target.split(marker,1)[1] if marker in target else ""

def localtime_zone(path=LOCALTIME):
    try: return zone_from_link(os.readlink(path))
    except OSError: pass
    try: return Path("/etc/timezone").read_text(encoding="utf-8").strip()   # Debian without the link
    except OSError: return ""

def zones_from_tree(root=ZONEINFO):
    """Every zone name under /usr/share/zoneinfo (files whose first bytes are TZif)."""
    found=[]
    for folder,dirs,files in os.walk(root):
        rel=os.path.relpath(folder,root)
        if rel!="." and rel.split(os.sep)[0] in _NOT_REGIONS: dirs[:]=[]; continue
        for name in files:
            path=os.path.join(folder,name)
            try:
                with open(path,"rb") as f:
                    if f.read(4)!=b"TZif": continue
            except OSError: continue
            zone=os.path.normpath(os.path.join(rel,name)).replace(os.sep,"/")
            if zone[:1].isupper(): found.append(zone)
    return sorted(found)

def list_zones():
    if have("timedatectl"):
        r=run(["timedatectl","list-timezones","--no-pager"],timeout=10)
        zones=[z.strip() for z in r.out.splitlines() if z.strip()] if r.ok else []
        if zones: return zones
    return zones_from_tree()

def read_state():
    s=TimeState(timedatectl=have("timedatectl"))
    if s.timedatectl:
        r=run(["timedatectl","show"],timeout=10)
        if r.ok: s.timezone,s.ntp,s.synced,s.can_ntp=parse_show(r.out)
        else: s.timedatectl=False
    if not s.timezone: s.timezone=localtime_zone() or "UTC"
    s.zones=list_zones()
    return s

# ---------------------------------------------------------------------- regions and cities
def split_zone(zone):
    """'America/Argentina/Buenos_Aires' -> ('America', 'Buenos Aires, Argentina'); 'UTC' -> ('Other', 'UTC')."""
    parts=zone.split("/")
    if len(parts)==1 or parts[0]=="Etc": return OTHER,parts[-1].replace("_"," ")   # Etc/UTC is UTC
    city=parts[-1].replace("_"," ")
    if len(parts)>2: city+=", "+", ".join(p.replace("_"," ") for p in reversed(parts[1:-1]))
    return parts[0],city

def regions(zones):
    """{region: [(zone, city), ...]} with the regions and the cities in alphabetical order (Other last)."""
    out={}
    for z in zones:
        if z.split("/")[0] in _NOT_REGIONS: continue
        region,city=split_zone(z); out.setdefault(region,[]).append((z,city))
    for cities in out.values(): cities.sort(key=lambda c:c[1].casefold())
    return dict(sorted(out.items(),key=lambda kv:(kv[0]==OTHER,kv[0])))

def zone_label(zone):
    region,city=split_zone(zone)
    return city if region==OTHER else f"{city} ({region})"

# ---------------------------------------------------------------------- changing (argv; run as the user first, then as root)
def ntp_argv(on): return ["timedatectl","set-ntp","true" if on else "false"]

def timezone_argv(zone, timedatectl=True):
    if timedatectl: return ["timedatectl","set-timezone",zone]
    return ["ln","-sfn",str(ZONEINFO/zone),str(LOCALTIME)]

def set_time_argv(when):
    """Set the clock to a datetime (local time). timedatectl refuses while network time is on."""
    return ["timedatectl","set-time",when.strftime("%Y-%m-%d %H:%M:00")]

# Settings > Date and time > Set the time: three ways to get to a time with a remote (model.TIME_ENTRY)
FIELDS=("year","month","day","hour","minute")
def adjust(when, field, delta):
    """`when` with one field moved by `delta`, wrapping within its range (day 31 + 1 is day 1 of the same month; a
    month change keeps the day inside the new month). Years stay between 2000 and 2099."""
    if field=="minute": return when.replace(minute=(when.minute+delta)%60)
    if field=="hour": return when.replace(hour=(when.hour+delta)%24)
    if field=="day":
        days=_days_in(when.year,when.month); return when.replace(day=(when.day-1+delta)%days+1)
    if field=="month":
        month=(when.month-1+delta)%12+1; return when.replace(month=month,day=min(when.day,_days_in(when.year,month)))
    if field=="year":
        year=min(2099,max(2000,when.year+delta)); return when.replace(year=year,day=min(when.day,_days_in(year,when.month)))
    raise ValueError(field)
def _days_in(year, month):
    nxt=datetime.date(year+(month==12),month%12+1,1); return (nxt-datetime.timedelta(days=1)).day
def step(when, minutes):
    """`when` moved forward (or back) by a number of minutes: the "steps" way."""
    return when+datetime.timedelta(minutes=minutes)
STEPS=((-1440,"−1 day"),(-60,"−1 h"),(-10,"−10 min"),(-1,"−1 min"),(1,"+1 min"),(10,"+10 min"),(60,"+1 h"),(1440,"+1 day"))
def from_digits(when, text):
    """The "digits" way: HHMM (or HMM) typed on the number pad, on the same day. Raises ValueError for a time that is not one."""
    t=(text or "").strip()
    if not t.isdigit() or len(t) not in (3,4): raise ValueError("Type the time as four digits, such as 1905 for 19:05 (7:05 PM).")
    hour,minute=int(t[:-2]),int(t[-2:])
    if hour>23 or minute>59: raise ValueError(f"{t[:-2]}:{t[-2:]} is not a time of day.")
    return when.replace(hour=hour,minute=minute,second=0,microsecond=0)

def valid_zone(zone, zones):
    return zone in zones and ".." not in zone and not zone.startswith("/")

# ---------------------------------------------------------------------- the Quick Menu's clock
def clock_text(when=None, hours24=False):
    """'14:05' or '2:05 PM'."""
    t=time.localtime(when)
    if hours24: return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    return f"{t.tm_hour%12 or 12}:{t.tm_min:02d} {'AM' if t.tm_hour<12 else 'PM'}"

def date_text(when=None):
    """'Thursday, October 15': day and month names in English, as the rest of TVWCS."""
    t=time.localtime(when)
    days=("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday")
    months=("January","February","March","April","May","June","July","August","September","October","November","December")
    return f"{days[t.tm_wday]}, {months[t.tm_mon-1]} {t.tm_mday}"
