"""TVWCS's lock screen: swaylock on a plain dark screen, with its ring in TVWCS's accent colour. A TVWCS session (TV
mode) always locks with it; a desktop session's own locker is left alone. Unlocking is as with any swaylock: type the
password and press Enter. No GTK dependency."""
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

def lock(settings=None):
    """`tvwcs lock`: start swaylock."""
    if not available():
        print("TVWCS's lock screen needs swaylock.",file=sys.stderr); return 1
    argv=locker_argv((settings or {}).get("accent","#0078d7"))
    os.execvp(argv[0],argv)
