"""TVWCS - TV Window Channel Switcher: a remote-friendly GTK 4 launcher for i3."""
import os
from pathlib import Path

try:  # single source of truth: the VERSION file at the repository root
    __version__ = (Path(__file__).resolve().parent.parent.parent / "VERSION").read_text(encoding="utf-8").strip()
except OSError:  # installed as a wheel without the repo tree
    __version__ = os.environ.get("TVWCS_VERSION", "0.0.0.dev0")
