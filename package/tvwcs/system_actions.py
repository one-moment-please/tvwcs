"""System actions offered by the System dialog; no GTK dependency."""
from __future__ import annotations
import os, shlex, shutil
from dataclasses import dataclass

@dataclass(frozen=True)
class SystemAction:
    id: str
    label: str
    icon: str          # symbolic icon name from the icon theme
    fallback: str      # text glyph used when the theme lacks the icon
    confirm: str = ""  # non-empty = ask for confirmation first; the text is the question

SYSTEM_ACTIONS=(
    SystemAction("lock","Lock","system-lock-screen-symbolic","🔒"),
    SystemAction("refresh","Refresh applications","view-refresh-symbolic","⟳"),
    SystemAction("sleep","Sleep","weather-clear-night-symbolic","☾"),
    SystemAction("logout","Log out","system-log-out-symbolic","⇥","Log out and end this session? Unsaved work in open applications may be lost."),
    SystemAction("reboot","Reboot","system-reboot-symbolic","↻","Restart the computer now? Unsaved work in open applications may be lost."),
    SystemAction("shutdown","Shut down","system-shutdown-symbolic","⏻","Power off the computer now? Unsaved work in open applications may be lost."),
)

def _sway(env,which): return bool(env.get("SWAYSOCK")) and bool(which("swaymsg"))

def logout_command(env=None, which=shutil.which):
    env=os.environ if env is None else env
    return ["swaymsg","exit"] if _sway(env,which) else ["i3-msg","exit"]

def lock_command(configured="", env=None, which=shutil.which):
    """A user-configured command wins; otherwise the first locker that is installed."""
    env=os.environ if env is None else env
    if configured and configured.strip():
        try:
            parts=shlex.split(configured)
            if parts: return parts
        except ValueError: pass
    candidates=[]
    if _sway(env,which): candidates.append(["swaylock","-f","-c","000000"])
    candidates+= [["i3lock","-c","000000"],["cinnamon-screensaver-command","--lock"],["xdg-screensaver","lock"],["loginctl","lock-session"]]
    for cmd in candidates:
        if which(cmd[0]): return cmd
    return ["loginctl","lock-session"]

def command_for(action_id, settings=None, env=None, which=shutil.which):
    settings=settings or {}
    if action_id=="lock": return lock_command(settings.get("lock_command",""),env,which)
    if action_id=="logout": return logout_command(env,which)
    return {"sleep":["systemctl","suspend"],"reboot":["systemctl","reboot"],"shutdown":["systemctl","poweroff"]}.get(action_id)
