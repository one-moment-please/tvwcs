"""Storage for Settings: the drives inside or plugged into the computer, and shares on the network. No GTK dependency.

Drives are read with lsblk and mounted, unmounted and switched off with udisksctl (UDisks), which lets the user at
the screen do that for USB drives without a password. Network shares (Windows/Samba smb://, NFS nfs://, SSH sftp://,
WebDAV dav://, FTP ftp://) are connected with `gio mount` (GVfs, the gvfs-backends package); their files then appear
under /run/user/<uid>/gvfs/ and in file managers. The addresses of saved shares are TVWCS options (network_shares);
passwords are never stored by TVWCS."""
from __future__ import annotations
import json, os, re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlparse

from tvwcs.control_cmd import have, run

SCHEMES=("smb","nfs","sftp","ssh","dav","davs","ftp","afp")
_SIZE_UNITS=("B","KB","MB","GB","TB","PB")

def size_text(n):
    """1500000000 -> '1.5 GB' (powers of 1000, as drives are sold)."""
    try: n=float(n or 0)
    except (TypeError,ValueError): return ""
    i=0
    while n>=1000 and i<len(_SIZE_UNITS)-1: n/=1000; i+=1
    return f"{n:.0f} {_SIZE_UNITS[i]}" if n>=100 or i==0 else f"{n:.1f} {_SIZE_UNITS[i]}"

@dataclass
class Volume:
    path: str            # /dev/sdb1
    name: str            # sdb1
    fstype: str = ""
    label: str = ""
    size: int = 0
    mountpoints: list = field(default_factory=list)
    used: int = 0
    avail: int = 0
    @property
    def mounted(self): return bool(self.mountpoints)
    @property
    def system(self):
        """Holds the running system (/, /boot, /home, swap...): shown, never unmounted from here."""
        return any(m in ("/","/boot","/boot/efi","/home","/usr","/var","[SWAP]") for m in self.mountpoints) or self.fstype=="swap"
    @property
    def title(self): return self.label or self.name

@dataclass
class Drive:
    path: str
    name: str
    model: str = ""
    size: int = 0
    removable: bool = False   # plugged in (USB, SD card): can be switched off before unplugging
    transport: str = ""
    volumes: list = field(default_factory=list)
    @property
    def system(self): return any(v.system for v in self.volumes)
    @property
    def title(self): return self.model or self.name

@dataclass
class Share:
    address: str
    connected: bool = False
    path: str = ""            # where its files are, when connected

@dataclass
class StorageState:
    drives: list = field(default_factory=list)
    shares: list = field(default_factory=list)
    udisks: bool = False
    gio: bool = False
    smb: bool = False         # GVfs's back ends for network shares are installed (gvfs-backends)
    message: str = ""

# ---------------------------------------------------------------------- reading drives
LSBLK=["lsblk","-J","-b","-o","NAME,PATH,TYPE,SIZE,FSTYPE,LABEL,MOUNTPOINTS,RM,HOTPLUG,MODEL,TRAN,FSUSED,FSAVAIL"]

def _int(v):
    try: return int(v or 0)
    except (TypeError,ValueError): return 0

def parse_lsblk(text):
    """`lsblk -J -b -o ...` -> [Drive]. Loop devices, RAM disks and CD drives without media are left out; a drive with
    a file system written straight on it (no partitions) is one volume."""
    try: data=json.loads(text or "{}")
    except ValueError: return []
    drives=[]
    def volumes(node):
        out=[]
        for child in node.get("children") or []:
            if child.get("fstype") or child.get("mountpoints") and any(child.get("mountpoints")):
                mps=[m for m in (child.get("mountpoints") or []) if m]
                out.append(Volume(child.get("path") or f"/dev/{child.get('name')}",child.get("name",""),child.get("fstype") or "",
                                  (child.get("label") or "").strip(),_int(child.get("size")),mps,_int(child.get("fsused")),_int(child.get("fsavail"))))
            out+=volumes(child)   # LVM and encrypted volumes sit under their partition
        return out
    for node in data.get("blockdevices",[]):
        if node.get("type") not in ("disk",) or node.get("name","").startswith(("loop","ram","zram")): continue
        d=Drive(node.get("path") or f"/dev/{node.get('name')}",node.get("name",""),(node.get("model") or "").strip(),_int(node.get("size")),
                bool(node.get("rm")) or bool(node.get("hotplug")),node.get("tran") or "")
        d.volumes=volumes(node)
        if node.get("fstype"):
            mps=[m for m in (node.get("mountpoints") or []) if m]
            d.volumes.insert(0,Volume(d.path,d.name,node.get("fstype"),(node.get("label") or "").strip(),d.size,mps,_int(node.get("fsused")),_int(node.get("fsavail"))))
        if d.size: drives.append(d)
    return sorted(drives,key=lambda d:(not d.system,d.removable,d.name))

# ---------------------------------------------------------------------- reading shares
def valid_address(address):
    """An address `gio mount` can connect: smb://server/share and the like. -> "" or why not."""
    a=(address or "").strip()
    u=urlparse(a)
    if u.scheme not in SCHEMES: return "Start the address with smb:// (Windows and Samba), nfs://, sftp://, dav:// or ftp://, such as smb://nas/videos."
    if not u.hostname: return "The address needs a computer's name or IP address after the //, such as smb://nas/videos."
    if any(c.isspace() for c in a): return "Write spaces in the address as %20."
    return ""

def share_label(address):
    """smb://nas.local/Videos -> 'Videos on nas.local'."""
    u=urlparse(address)
    folder=unquote(u.path.strip("/")) if u.path else ""
    return f"{folder} on {u.hostname}" if folder else (u.hostname or address)

def parse_gio_mounts(text):
    """`gio mount -l` -> the addresses of the mounted network locations (the "Mount(...)" lines' URIs)."""
    found=[]
    for line in text.splitlines():
        m=re.search(r"Mount\(\d+\):.*?->\s*(\S+://\S+)",line)
        if m: found.append(m.group(1).rstrip("/"))
    return found

def same_share(a, b):
    """Two addresses for the same share ("smb://nas/videos" and "smb://nas/videos/")."""
    norm=lambda x:(x or "").strip().rstrip("/").lower()
    return norm(a)==norm(b)

def gvfs_path(address, uid=None):
    """Where GVfs shows a connected share's files: /run/user/1000/gvfs/smb-share:server=nas,share=videos."""
    uid=os.getuid() if uid is None else uid
    u=urlparse(address)
    if u.scheme=="smb":
        parts=[p for p in u.path.split("/") if p]
        name=f"smb-share:server={u.hostname},share={unquote(parts[0]).lower()}" if parts else f"smb-server:server={u.hostname}"
        if u.username: name+=f",user={u.username}"
    else: name=f"{u.scheme}:host={u.hostname}"+(f",port={u.port}" if u.port else "")+(f",user={u.username}" if u.username else "")
    return f"/run/user/{uid}/gvfs/{name}"

def _gvfs_backend(name):
    return any(os.path.exists(f"{d}/{name}") for d in ("/usr/libexec","/usr/lib/gvfs","/usr/libexec/gvfs","/usr/lib/x86_64-linux-gnu/gvfs"))

def read_state(saved=()):
    s=StorageState(udisks=have("udisksctl"),gio=have("gio"),smb=_gvfs_backend("gvfsd-smb"))
    if have("lsblk"):
        r=run(LSBLK,timeout=10)
        s.drives=parse_lsblk(r.out) if r.ok else []
        if not r.ok: s.message=r.message
    else: s.message="lsblk was not found (util-linux)."
    mounted=parse_gio_mounts(run(["gio","mount","-l"],timeout=10).out) if s.gio else []
    for address in saved:
        on=any(same_share(address,m) or m.lower().startswith(address.rstrip("/").lower()) for m in mounted)
        s.shares.append(Share(address,on,gvfs_path(address) if on else ""))
    return s

# ---------------------------------------------------------------------- changing (each -> "" when it worked, else why not)
def _outcome(r, otherwise):
    if r.ok: return ""
    text=(r.err or r.out or "").strip()
    if "NotAuthorized" in text or "not authorized" in text.lower(): return "This user may not do that without an administrator's password (polkit)."
    return text.splitlines()[-1] if text else otherwise

def mount(volume): return _outcome(run(["udisksctl","mount","--no-user-interaction","-b",volume],timeout=30),"The drive could not be opened.")
def unmount(volume): return _outcome(run(["udisksctl","unmount","--no-user-interaction","-b",volume],timeout=30),"The drive is still in use. Close what uses it, then try again.")
def power_off(drive): return _outcome(run(["udisksctl","power-off","--no-user-interaction","-b",drive],timeout=30),"The drive could not be switched off.")

def connect_answers(user="", password="", domain=""):
    """What `gio mount` reads from its input for a password-protected share: user, domain (SMB), password."""
    return f"{user}\n{domain}\n{password}\n"

def connect(address, user="", password=""):
    """Connect a share. With no user name it is tried as a guest (anonymous)."""
    if not user: return _outcome(run(["gio","mount","-a",address],timeout=60),"The share could not be connected.")
    r=run(["gio","mount",address],timeout=60,input=connect_answers(user,password))
    if r.ok: return ""
    text=(r.err or r.out or "")
    if "denied" in text.lower() or "password" in text.lower(): return "The user name or password was not accepted."
    return _outcome(r,"The share could not be connected.")

def disconnect(address): return _outcome(run(["gio","mount","-u",address],timeout=30),"The share could not be disconnected.")
