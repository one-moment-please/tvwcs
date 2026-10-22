"""TVWCS's lock screen: swaylock on a plain dark screen, with its ring in TVWCS's accent colour. A TVWCS session (TV
mode) always locks with it; a desktop session's own locker is left alone. Unlocking is as with any swaylock: type the
password and press Enter. No GTK dependency.

"Lock the screen when TVWCS starts" (Settings > User, the "lock_at_start" setting): the session's config runs
`tvwcs lock-at-start` as sway starts, which locks straight away in a TVWCS session, for computers that log in
automatically. It never locks an account without a usable password, which could not be unlocked."""
from __future__ import annotations
import os, re, shutil, sys
from pathlib import Path

BACKGROUND="1b1b1b"

def available(which=shutil.which):
    """True when swaylock is installed."""
    return bool(which("swaylock"))

def launcher():
    """The tvwcs launcher script, next to the package (as main.LAUNCHER finds it)."""
    here=Path(__file__).resolve().parent
    for cand in (here.parent/"bin"/"tvwcs",here/"tvwcs",here.parent.parent/"bin"/"tvwcs"):
        if cand.exists(): return str(cand)
    return "tvwcs"

def command(settings, env=None, which=shutil.which):
    """`tvwcs lock` in TV mode (a TVWCS session) when swaylock is installed, else None (the desktop's usual locker)."""
    from tvwcs.model import tv_mode
    if not tv_mode(env) or not available(which): return None
    return [launcher(),"lock"]

def locker_argv(accent="#0078d7"):
    """swaylock's command line. -f: it goes to the background once the screen is locked; -e: an empty Enter is not a
    wrong password; -F: failed attempts show. The ring (shown while typing) is in the accent colour."""
    ring=accent[1:].lower() if isinstance(accent,str) and re.fullmatch(r"#[0-9a-fA-F]{6}",accent) else "0078d7"
    return ["swaylock","-f","-e","-F","-c",BACKGROUND,"--ring-color",ring,"--key-hl-color","ffffff",
            "--inside-color",BACKGROUND,"--line-color",BACKGROUND,"--separator-color",BACKGROUND]

def can_unlock(status) -> bool:
    """False when `passwd -S` says the account has no password or a locked one: swaylock would never let it back in."""
    return status not in ("NP","L")

def lock_at_start(settings, env=None, which=shutil.which, status=None) -> str:
    """Why the session does not start locked, or "" when it does."""
    from tvwcs.account import password_status
    if not settings.get("lock_at_start"): return "off"
    if command(settings,env,which) is None: return "not a TVWCS session, or swaylock is not installed"
    if not can_unlock(password_status() if status is None else status): return "the account has no password to unlock it with"
    return ""

def lock(settings=None):
    """`tvwcs lock`: start swaylock."""
    if not available():
        print("TVWCS's lock screen needs swaylock.",file=sys.stderr); return 1
    argv=locker_argv((settings or {}).get("accent","#0078d7"))
    os.execvp(argv[0],argv)

def main(args):
    """`tvwcs lock` and `tvwcs lock-at-start` (the launcher runs these without loading GTK)."""
    from tvwcs.model import ConfigStore
    settings=ConfigStore().settings
    if args==["lock-at-start"]:
        why=lock_at_start(settings)
        if why: return 0 if why=="off" else (print(f"TVWCS: not locking at start: {why}.",file=sys.stderr) or 0)
    return lock(settings)

if __name__=="__main__": raise SystemExit(main(sys.argv[1:]))
