"""Flatpak's folders in XDG_DATA_DIRS. A module of its own, with no TVWCS imports: an older Settings app that has just
installed an update imports the new main.py, which imports this, while the old versions of TVWCS's other modules are
still loaded in it. A name main.py needs from them that only the new version has would break that restart."""
from __future__ import annotations

def with_flatpak_data_dirs(value: str | None, data_home: str) -> str:
    """XDG_DATA_DIRS with Flatpak's exports folders added the way flatpak's own profile script adds them (the user's,
    then the system's, before the rest), when they are missing: a session started before Flatpak was installed, or
    one whose login never ran that script (startx from a console). TVWCS sets this for itself at start-up, so GLib finds
    the apps' launchers and GTK their icons, and the apps it starts inherit it."""
    dirs=[d for d in (value or "/usr/local/share:/usr/share").split(":") if d]
    missing=[d for d in (f"{data_home}/flatpak/exports/share","/var/lib/flatpak/exports/share") if d not in dirs and d+"/" not in dirs]
    return ":".join(missing+dirs)
