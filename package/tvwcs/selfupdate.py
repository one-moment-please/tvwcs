"""Updating TVWCS itself from its GitHub releases: find the latest published release, compare it with the
running version, download its zip, run the zip's install.sh into the current install folder and clean up.
No GTK here, so it can be tested without a display; the Settings panel runs these calls on a worker thread."""
from __future__ import annotations
import json, os, re, subprocess, tempfile, urllib.error, urllib.request, zipfile
from dataclasses import dataclass
from pathlib import Path

GITHUB_REPO="one-moment-please/tvwcs"
LATEST_URL=f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
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
    return Release(".".join(map(str,parse_version(tag))),tag,asset["browser_download_url"],str(data.get("html_url") or ""))

def _open(url,accept):
    req=urllib.request.Request(url,headers={"Accept":accept,"User-Agent":"TVWCS-updater"})
    return urllib.request.urlopen(req,timeout=TIMEOUT)

def latest_release():
    try:
        with _open(LATEST_URL,"application/vnd.github+json") as r: data=json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code==404: raise UpdateError(f"No published release was found for {GITHUB_REPO} on GitHub.") from exc
        raise UpdateError(f"GitHub answered {exc.code} {exc.reason}.") from exc
    except (urllib.error.URLError,OSError,ValueError) as exc:
        raise UpdateError(f"Could not reach GitHub: {getattr(exc,'reason',exc)}") from exc
    return release_from_json(data)

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

def install_release(release,dest,migrate=False):
    """Download the release zip into a temporary folder, run its install.sh into `dest`, and delete the
    temporary folder whatever happens. `migrate`: the user agreed to move TVWCS from its old location, so install.sh
    updates the include line in the window manager config and deletes the old copy. Returns install.sh's output."""
    with tempfile.TemporaryDirectory(prefix="tvwcs-update-") as tmp:
        tmp=Path(tmp); archive=tmp/"release.zip"; unpacked=tmp/"unpacked"
        _download(release.zip_url,archive)
        try:
            with zipfile.ZipFile(archive) as z: z.extractall(unpacked)   # extractall drops absolute and ".." paths
        except zipfile.BadZipFile as exc: raise UpdateError("The downloaded file is not a valid zip.") from exc
        script=unpacked/"tvwcs"/"install.sh"
        if not script.is_file() or not (unpacked/"tvwcs"/"tvwcs"/"main.py").is_file():
            raise UpdateError("The downloaded zip does not look like a TVWCS release.")
        env={**os.environ,"TVWCS_DEST":str(dest),"TVWCS_NO_RESTART":"1"}   # TVWCS restarts itself afterwards
        if migrate: env["TVWCS_MIGRATE"]="1"
        try:
            done=subprocess.run(["sh",str(script)],cwd=str(unpacked/"tvwcs"),env=env,stdin=subprocess.DEVNULL,
                                capture_output=True,text=True,timeout=120)
        except (OSError,subprocess.TimeoutExpired) as exc: raise UpdateError(f"Could not run install.sh: {exc}") from exc
        if done.returncode!=0: raise UpdateError("install.sh failed:\n"+(done.stderr or done.stdout).strip()[-600:])
        return done.stdout
