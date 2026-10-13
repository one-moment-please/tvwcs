"""Updates backend for the Applications window's Updates tab: a thin, testable layer over apt.

The GUI never shells out directly; it calls these functions. Parsing lives here as pure helpers so
the list of pending upgrades can be unit-tested from saved `apt` output. Privileged steps
(`apt update`, `apt install`) run through `sudo -n` and report a friendly message when sudo needs a
password or is not configured.

Package kinds:
  security  — offered from a *security* repository source line
  thirdparty— offered from a source that is not one of the OS's own repositories
              (no "origin=" match in /etc/apt/sources.list(.d) entries and not a security pocket)
  software  — everything else (the distro's main repos)
"""
from __future__ import annotations
import glob, os, re, shutil, subprocess

from tvwcs.network import run

# ------------------------------------------------------------------ parsing (pure)

_UPGRADE_HDR = "Listing..."
_PKG_LINE = re.compile(r"^(?P<pkg>\S+) (?P<old>\S+) (?P<new>\S+) (?P<size>[0-9.]+\w?)$")
_SECTION = re.compile(r"Section: (.*)")
_ORIGIN = re.compile(r"Origin: (.*)")
_DESC_START = re.compile(r"^Description: ")

def parse_upgrades(text):
    """`apt list --upgradable` (machine-ish output) -> [{'package','current','candidate','size'}].
    Lines look like:  bash/nobody 5.1-2ubuntu2 [upgradable to: 5.1-2ubuntu3] 603 kB
    The two accepted forms (with and without the size tail) are both handled."""
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line == _UPGRADE_HDR or "is upgradable" not in line:
            continue
        m = re.match(r"^(?P<pkg>\S+?)(?:/(?P<repo>\S+))? .*\[upgradable to:\s*(?P<new>[^\]]+)\]", line)
        if not m:
            continue
        size = ""
        sm = re.search(r"(\d+(?:\.\d+)?\s*[kKmMbB])\s*$", line)
        if sm:
            size = sm.group(1).replace(" ", "")
        old = ""
        om = re.match(r"^\S+?(?:/\S+)? (\S+) \[", line)
        if om:
            old = om.group(1)
        items.append({"package": m.group("pkg"), "current": old, "candidate": m.group("new").strip(), "size": size})
    return items

def parse_curlish_upgrades(text):
    """Alternative parser for `apt-get -s upgrade` style lines: 'Inst pkg (new old repo)'."""
    items = []
    for line in text.splitlines():
        m = re.match(r"^Inst (\S+) \((\S+) (\S+) ", line)
        if m:
            items.append({"package": m.group(1), "candidate": m.group(2), "current": m.group(3), "size": ""})
    return items

_SECURITY_MARKS = ("security", "safe-update", "update-mint", "-updates")

def classify(package, candidate, origin="", sources=""):
    """-> 'security' | 'thirdparty' | 'software'. `sources` is the CandidateOrigin/URI text from apt-cache."""
    blob = f"{origin} {sources}".lower()
    if "security" in blob or "safe-update" in blob:
        return "security"
    # Known distro origins keep 'software'; anything with an unusual origin is third-party.
    if origin and not re.search(r"(ubuntu|debian|linuxmint|lmde|ppa.launchpad|archive|security)", blob):
        return "thirdparty"
    return "software"

def parse_showtext(text):
    """`apt-cache show <pkg>` stanza -> {'description','homepage','section','maintainer','installed','candidate','size'}"""
    info = {"description": "", "homepage": "", "section": "", "maintainer": "", "installed": "", "candidate": "", "size": ""}
    lines = text.splitlines()
    key = None
    desc = []
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        if _DESC_START.match(line):
            key = "description"; desc.append(line[len("Description:"):].strip()); continue
        m = re.match(r"^([A-Za-z-]+):\s*(.*)$", line)
        if m:
            if key == "description":
                break                      # only the first Description paragraph
            k = m.group(1).lower().replace("-", "_")
            if k in info:
                info[k] = m.group(2).strip()
            key = k
            continue
        if line.startswith((" ", "\t")) and key == "description":
            cont = line.strip()
            if cont.startswith(("#", "This lists", "This package provides")) or True:
                desc.append(cont)
    info["description"] = " ".join(d for d in desc if d and not d.startswith("."))[:800]
    return info

def parse_depends(text):
    """Depends/Recommends/Suggests lines of an apt-cache show stanza -> dict of lists."""
    out = {}
    for name in ("Depends", "Recommends", "Suggests", "Breaks", "Replaces"):
        m = re.search(rf"^{name}: (.*)$", text, re.M)
        if m:
            out[name] = [p.strip() for p in m.group(1).split(",") if p.strip()]
    return out

def parse_rdepends(text):
    """`apt-cache rdepends --recurse=1 <pkg>` output -> list of package names."""
    names = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("Reverse", "Depends", "Recommends", "Suggests")):
            continue
        names.append(stripped.lstrip("|").strip())
    seen, unique = set(), []
    for n in names:
        if n and n not in seen:
            seen.add(n); unique.append(n)
    return unique

def read_sources_origin_map(paths=None):
    """Map 'origin=' strings found in the system's APT sources, used to tell distro vs third-party repos."""
    paths = paths or sorted(glob.glob("/etc/apt/sources.list") + glob.glob("/etc/apt/sources.list.d/*"))
    origins = set()
    for path in paths:
        try:
            if os.path.isdir(path):
                continue
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    m = re.search(r"origin=([^,\s]+)", line)
                    if m:
                        origins.add(m.group(1).lower())
        except OSError:
            continue
    return origins

# ------------------------------------------------------------------ commands

def apt_available():
    return shutil.which("apt") is not None and shutil.which("apt-cache") is not None

def list_upgrades():
    ok, out = run(["apt", "list", "--upgradable"], timeout=120)
    if not ok:
        return [], out
    return parse_upgrades(out), ""

def refresh_lists():
    """sudo -n apt update; -> (ok, message)."""
    try:
        proc = subprocess.run(["sudo", "-n", "apt", "update"], capture_output=True, text=True, timeout=900)
    except FileNotFoundError:
        return False, "sudo is not installed; run TVWCS updates from a terminal instead."
    except subprocess.SubprocessError as exc:
        return False, str(exc)
    if proc.returncode == 0:
        return True, ""
    err = (proc.stderr or proc.stdout or "").strip()
    if "password is required" in err.lower() or "sudo:" in err.lower() and "password" in err.lower():
        return False, "TVWCS cannot run “apt update” without a password. Configure sudo (or run the update from a terminal)."
    return False, err.splitlines()[-1] if err else "apt update failed."

def install_selected(packages):
    """sudo -n apt-get install --yes <packages>; -> (ok, message). Empty selection returns success."""
    if not packages:
        return True, "Nothing selected."
    argv = ["sudo", "-n", "apt-get", "install", "--yes", "--"] + list(packages)
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=3600)
    except FileNotFoundError:
        return False, "sudo is not installed; run TVWCS updates from a terminal instead."
    except subprocess.SubprocessError as exc:
        return False, str(exc)
    if proc.returncode == 0:
        return True, ""
    err = (proc.stderr or proc.stdout or "").strip()
    return False, err.splitlines()[-1] if err else "Installation failed."

def policy_version(package):
    _, out = run(["apt-cache", "policy", package])
    installed = candidate = ""
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Installed:"):
            installed = line.split(":", 1)[1].strip()
        elif line.startswith("Candidate:"):
            candidate = line.split(":", 1)[1].strip()
    return installed, candidate

def package_info(package):
    """Everything the right-hand details pane shows for one upgrade entry."""
    _, show = run(["apt-cache", "show", package])
    info = parse_showtext(show)
    info["depends"] = parse_depends(show)
    installed, candidate = policy_version(package)
    info["installed"] = installed or info["installed"]
    info["candidate"] = candidate or info["candidate"]
    _, origin_out = run(["apt-cache", "policy", package])
    m = re.search(r"^\s+\*\*\s+\S+\s+(\S+)", origin_out, re.M)
    info["origin"] = m.group(1) if m else ""
    changelog = get_changelog(package, candidate)
    info["changelog"] = changelog
    return info

def get_changelog(package, version):
    """Try `apt-change`/`debchange` then the online Debian/Ubuntu changelog URL as a fallback string."""
    for tool in (["apt-news"], ["debchange", "--list", package]):
        ok, out = run(tool, timeout=20)
        if ok and out.strip():
            return out.strip()[:4000]
    if version:
        return f"No local changelog was found for {package}. See https://tracker.debian.org/pkg/{package} or the package's homepage above."
    return ""

def affected_packages(package):
    """Packages that depend on this one (roughly: what installing it touches)."""
    _, rev = run(["apt-cache", "rdepends", "--recurse=1", package], timeout=60)
    return parse_rdepends(rev)[:50]

def download_size_label(items):
    total_kb = 0.0
    for item in items:
        size = item.get("size", "")
        m = re.match(r"([0-9.]+)([kKmMbB])", size)
        if not m:
            continue
        value = float(m.group(1))
        unit = m.group(2).lower()
        total_kb += value if unit == "k" else value * 1024 if unit == "m" else value / 1024
    if total_kb >= 1024:
        return f"{total_kb/1024:.1f} MB"
    return f"{int(total_kb)} kB"
