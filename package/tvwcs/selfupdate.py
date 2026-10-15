"""Updating TVWCS itself from its GitHub releases: find the latest published release (or, for those who want them,
the newest prerelease), compare it with the running version, download its zip, run the zip's install.sh into the
current install folder and clean up. Each merged change is released as a prerelease first and marked latest once
it has been tested, so "the latest release" is also what a prerelease rolls back to.
No GTK here, so it can be tested without a display; the Settings panel runs these calls on a worker thread."""
from __future__ import annotations
import json, os, re, shutil, subprocess, tempfile, urllib.error, urllib.request, zipfile
from dataclasses import dataclass
from pathlib import Path

GITHUB_REPO="one-moment-please/tvwcs"
LATEST_URL=f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_URL=f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=30"
MAX_DOWNLOAD=50*1024*1024   # a release zip is a few hundred KB; anything near this is not one
TIMEOUT=20

class UpdateError(Exception):
    """A readable reason the check or the install did not work."""

@dataclass
class Release:
    version: str
    tag: str
    zip_url: str
    page_url: str
    prerelease: bool = False

def parse_version(text):
    """'v2.6.0' or '2.6.0' -> (2, 6, 0). Anything after the numbers (such as '-beta.2') is ignored."""
    m=re.match(r"\s*v?(\d+(?:\.\d+)*)",text or "")
    if not m: raise UpdateError(f"Cannot read the version number “{text}”.")
    return tuple(int(n) for n in m.group(1).split("."))

def is_newer(candidate,current):
    a,b=parse_version(candidate),parse_version(current)
    width=max(len(a),len(b))
    return a+(0,)*(width-len(a)) > b+(0,)*(width-len(b))

def release_from_json(data):
    """Pick the version and the release zip out of GitHub's /releases/latest answer."""
    tag=str(data.get("tag_name") or "")
    zips=[a for a in data.get("assets") or [] if str(a.get("name","")).lower().endswith(".zip")]
    asset=next((a for a in zips if re.fullmatch(r"TVWCS-[\d.]+\.zip",str(a.get("name","")))),zips[0] if zips else None)
    if not tag or asset is None: raise UpdateError("The latest release on GitHub has no TVWCS zip attached.")
    return Release(".".join(map(str,parse_version(tag))),tag,asset["browser_download_url"],str(data.get("html_url") or ""),
                   bool(data.get("prerelease")))

def newest_release(items):
    """The newest version among GitHub's /releases list, prereleases included; drafts and releases without a TVWCS
    zip are skipped. None when there is none."""
    found=[]
    for data in items if isinstance(items,list) else []:
        if not isinstance(data,dict) or data.get("draft"): continue
        try: found.append(release_from_json(data))
        except UpdateError: continue
    return max(found,key=lambda r:parse_version(r.version),default=None)

def _open(url,accept):
    req=urllib.request.Request(url,headers={"Accept":accept,"User-Agent":"TVWCS-updater"})
    return urllib.request.urlopen(req,timeout=TIMEOUT)

def _get_json(url):
    try:
        with _open(url,"application/vnd.github+json") as r: return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code==404: raise UpdateError(f"No published release was found for {GITHUB_REPO} on GitHub.") from exc
        raise UpdateError(f"GitHub answered {exc.code} {exc.reason}.") from exc
    except (urllib.error.URLError,OSError,ValueError) as exc:
        raise UpdateError(f"Could not reach GitHub: {getattr(exc,'reason',exc)}") from exc

def latest_release(prereleases=False):
    """The release marked latest on GitHub; with prereleases, the newest release of all, when that is newer."""
    latest=release_from_json(_get_json(LATEST_URL))
    if not prereleases: return latest
    newest=newest_release(_get_json(RELEASES_URL))
    return newest if newest is not None and is_newer(newest.version,latest.version) else latest

def default_dir():
    """Where install.sh puts TVWCS: ~/.local/share/tvwcs (XDG_DATA_HOME)."""
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home()/".local"/"share")/"tvwcs"

def legacy_dir():
    """Where TVWCS 2.6 and older were installed: ~/.config/i3/tvwcs."""
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home()/".config")/"i3"/"tvwcs"

def update_target(current):
    """Where an update of the install in `current` goes: the same folder, except that one in the old location
    moves to the new default."""
    if current is not None and Path(current).resolve()==legacy_dir().resolve(): return default_dir()
    return current

def install_dir(package_dir):
    """The folder install.sh put TVWCS in (it holds tvwcs.conf and bin/tvwcs next to the package), or None when
    running from a source checkout, which is updated with git instead."""
    root=Path(package_dir).resolve().parent
    return root if (root/"tvwcs.conf").is_file() and (root/"bin"/"tvwcs").is_file() else None

def _download(url,target):
    try:
        with _open(url,"application/octet-stream") as r, open(target,"wb") as out:
            total=0
            while chunk:=r.read(65536):
                total+=len(chunk)
                if total>MAX_DOWNLOAD: raise UpdateError("The download is far larger than a TVWCS release; stopped.")
                out.write(chunk)
    except (urllib.error.URLError,OSError) as exc:
        raise UpdateError(f"Download failed: {getattr(exc,'reason',exc)}") from exc

def download_release(release):
    """Download the release zip and unpack it in a new temporary folder. Returns the folder; the caller deletes it
    (discard) once it has been installed or the update was cancelled."""
    tmp=Path(tempfile.mkdtemp(prefix="tvwcs-update-"))
    try:
        archive=tmp/"release.zip"; unpacked=tmp/"unpacked"
        _download(release.zip_url,archive)
        try:
            with zipfile.ZipFile(archive) as z: z.extractall(unpacked)   # extractall drops absolute and ".." paths
        except zipfile.BadZipFile as exc: raise UpdateError("The downloaded file is not a valid zip.") from exc
        if not (unpacked/"tvwcs"/"install.sh").is_file() or not (unpacked/"tvwcs"/"tvwcs"/"main.py").is_file():
            raise UpdateError("The downloaded zip does not look like a TVWCS release.")
    except BaseException:
        discard(tmp); raise
    return tmp

def discard(folder): shutil.rmtree(folder,ignore_errors=True)

def parse_missing(text):
    """install.sh --missing output -> [(packages, what for)]."""
    out=[]
    for line in (text or "").splitlines():
        parts=line.split("\t")
        if len(parts)==3 and parts[0]=="need" and parts[1].strip(): out.append((parts[1].strip(),parts[2].strip()))
    return out

def missing_packages(folder):
    """The packages the downloaded release needs that are not installed here, so they can be installed first.
    Releases before 3.1 cannot say ([]): their install.sh has no --missing and would install instead of answering."""
    script=Path(folder)/"unpacked"/"tvwcs"/"install.sh"
    try:
        if "--missing" not in script.read_text(errors="replace"): return []
        done=subprocess.run(["sh",str(script),"--missing"],cwd=str(script.parent),stdin=subprocess.DEVNULL,
                            capture_output=True,text=True,timeout=60)
    except (OSError,subprocess.TimeoutExpired): return []
    return parse_missing(done.stdout) if done.returncode==0 else []

def install_packages_argv(packages):
    """The root command that installs the packages a release needs (apt; Debian is the supported system)."""
    names=[p for group in packages for p in group.split()]
    if not names or not all(re.fullmatch(r"[a-z0-9][a-z0-9+.-]*",n) for n in names): raise ValueError("Unexpected package name.")
    return ["env","DEBIAN_FRONTEND=noninteractive","sh","-c",'apt-get update -q && apt-get install -y "$@"',"sh",*names]

def install_downloaded(folder,dest,migrate=False):
    """Run the downloaded release's install.sh into `dest`. Returns install.sh's output."""
    unpacked=Path(folder)/"unpacked"
    env={**os.environ,"TVWCS_DEST":str(dest),"TVWCS_NO_RESTART":"1"}   # TVWCS restarts itself afterwards
    if migrate: env["TVWCS_MIGRATE"]="1"
    try:
        done=subprocess.run(["sh",str(unpacked/"tvwcs"/"install.sh")],cwd=str(unpacked/"tvwcs"),env=env,stdin=subprocess.DEVNULL,
                            capture_output=True,text=True,timeout=120)
    except (OSError,subprocess.TimeoutExpired) as exc: raise UpdateError(f"Could not run install.sh: {exc}") from exc
    if done.returncode!=0: raise UpdateError("install.sh failed:\n"+(done.stderr or done.stdout).strip()[-600:])
    return done.stdout

def install_release(release,dest,migrate=False):
    """Download the release zip into a temporary folder, run its install.sh into `dest`, and delete the
    temporary folder whatever happens. `migrate`: the user agreed to move TVWCS from its old location, so install.sh
    updates the include line in the window manager config and deletes the old copy. Returns install.sh's output."""
    folder=download_release(release)
    try: return install_downloaded(folder,dest,migrate)
    finally: discard(folder)
