"""System actions offered by the Quick Menu's power menu; no GTK dependency.

Power actions use systemd when it runs the system, else elogind's loginctl (Artix, Gentoo, Void, Devuan and others
without systemd), else the plain commands (zzz, reboot, poweroff), which usually need root without either."""
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

POWER_MENU=("lock","sleep","reboot","shutdown","logout")   # the power menu's order; lock and logout only when they apply
DISPLAY_MANAGERS=("gdm","gdm3","lightdm","sddm","lxdm","xdm","slim","greetd","ly","entrance","emptty")

def login_manager_installed(exists=os.path.exists, which=shutil.which):
    """True when a login screen (display manager) is installed. Without one, logging out of i3 or sway only leaves a text
    console, so the power menu offers Log out only with one."""
    if exists("/etc/systemd/system/display-manager.service"): return True
    try:
        with open("/etc/X11/default-display-manager",encoding="utf-8") as f:
            if f.read().strip(): return True
    except OSError: pass
    return any(which(name) for name in DISPLAY_MANAGERS)

def power_menu(settings=None, display_manager=None):
    """The actions the Quick Menu's power menu offers, in order."""
    settings=settings or {}
    dm=login_manager_installed() if display_manager is None else display_manager
    by_id={a.id:a for a in SYSTEM_ACTIONS}
    return [by_id[i] for i in POWER_MENU if (i!="lock" or settings.get("quick_lock_button")) and (i!="logout" or dm)]

def _sway(env,which): return bool(env.get("SWAYSOCK")) and bool(which("swaymsg"))

def logout_command(env=None, which=shutil.which):
    env=os.environ if env is None else env
    return ["swaymsg","exit"] if _sway(env,which) else ["i3-msg","exit"]

POWER_VERBS={"sleep":"suspend","reboot":"reboot","shutdown":"poweroff"}
PLAIN_POWER={"sleep":(("zzz",),("pm-suspend",),("loginctl","suspend")),"reboot":(("reboot",),),"shutdown":(("poweroff",),)}

def systemd_running(exists=os.path.isdir):
    """sd_booted(): systemd is the init system when this folder exists."""
    return exists("/run/systemd/system")

def power_command(action_id, which=shutil.which, systemd=None):
    """How to suspend, reboot or power off here, or None when nothing installed can."""
    verb=POWER_VERBS[action_id]
    if (systemd_running() if systemd is None else systemd) and which("systemctl"): return ["systemctl",verb]
    if which("loginctl"): return ["loginctl",verb]   # elogind (systemd's own loginctl only gets here without systemd running)
    return next((list(c) for c in PLAIN_POWER[action_id] if which(c[0])),None)

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
    return next((cmd for cmd in candidates if which(cmd[0])),None)

def command_for(action_id, settings=None, env=None, which=shutil.which, systemd=None):
    """The command for a system action, or None when this system has nothing that does it (or it is not a command)."""
    settings=settings or {}
    if action_id=="lock": return lock_command(settings.get("lock_command",""),env,which)
    if action_id=="logout": return logout_command(env,which)
    if action_id in POWER_VERBS: return power_command(action_id,which,systemd)
    return None

def unavailable_message(action_id):
    if action_id=="lock":
        return ("No screen locker was found. Install one (such as i3lock, or swaylock on sway), or set "
                "\"lock_command\" in ~/.config/tvwcs/config.json.")
    return "Nothing on this system can do that: TVWCS needs systemd, elogind (loginctl), or the reboot/poweroff/zzz commands."
