"""Workspace-centric view of the open windows. No GTK dependency.

TVWCS treats a workspace as the unit you switch between: an app on a workspace of its own is listed as that
app; apps sharing a workspace are grouped into one workspace entry named after what is in it."""
from __future__ import annotations
import re
from dataclasses import dataclass, field

_SUFFIXES=(" Web Browser"," Browser")

def short_app_name(name):
    for suffix in _SUFFIXES:
        if name and name.endswith(suffix) and len(name)>len(suffix): return name[:-len(suffix)]
    return name or ""

def window_app_name(window, match):
    """Friendly name of the application a window belongs to."""
    app=match(window)
    if app: return short_app_name(app.name)
    cls=(window.get("class") or window.get("instance") or "").replace("-"," ").replace("_"," ").strip()
    return cls[:1].upper()+cls[1:] if cls else (window.get("title") or "Window")

def workspace_label(windows, match, limit=3):
    """'Brave + Text Editor': the distinct apps on a workspace, in window order."""
    names=[]
    for w in windows:
        n=window_app_name(w,match)
        if n not in names: names.append(n)
    shown=names[:limit]; extra=len(names)-len(shown)
    return " + ".join(shown)+(f" + {extra} more" if extra>0 else "")

@dataclass
class WorkspaceEntry:
    name: str                      # the i3 workspace name (what i3-msg needs)
    label: str                     # what TVWCS shows
    windows: list = field(default_factory=list)
    output: str = ""
    visible: bool = False
    focused: bool = False
    urgent: bool = False
    @property
    def shared(self): return len(self.windows)>1

def _sort_key(name):
    m=re.match(r"\s*(\d+)",name or "")
    return (0,int(m.group(1)),name.casefold()) if m else (1,0,(name or "").casefold())

def build_entries(windows, workspaces, match):
    """One entry per workspace that has windows, plus one per window parked outside any workspace."""
    meta={w.get("name"):w for w in workspaces}
    buckets={}; parked=[]
    for win in windows:
        ws=win.get("workspace") or ""
        if not ws or ws.startswith("__i3"): parked.append(win)
        else: buckets.setdefault(ws,[]).append(win)
    entries=[]
    for name in sorted(buckets,key=_sort_key):
        wins=buckets[name]; m=meta.get(name,{})
        entries.append(WorkspaceEntry(name,workspace_label(wins,match),wins,m.get("output") or wins[0].get("output",""),
                                      bool(m.get("visible")),bool(m.get("focused")),bool(m.get("urgent")) or any(w.get("urgent") for w in wins)))
    for win in parked:
        entries.append(WorkspaceEntry(win.get("workspace") or "",window_app_name(win,match),[win],win.get("output",""),urgent=bool(win.get("urgent"))))
    return entries
