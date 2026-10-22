"""The TVWCS logo shown while the computer starts, in place of the start-up text (Settings > User > Logging in). No GTK
dependency.

The logo is a package of its own, tvwcs-boot-logo: a Plymouth theme (see data/plymouth), set as the default theme with
GRUB's "splash" option by the package's own scripts. Settings turns it on by installing that package from the GitHub
release of the running version, and off by removing it."""
from __future__ import annotations
import os
from tvwcs import selfupdate

PACKAGE="tvwcs-boot-logo"
THEME="/usr/share/plymouth/themes/tvwcs/tvwcs.plymouth"

def installed(exists=os.path.exists) -> bool:
    return exists(THEME)

def download(version):
    """Download this version's boot logo package. Returns (folder, [file]); the caller discards the folder."""
    release=selfupdate.Release(version,f"v{version}",{PACKAGE:selfupdate.deb_url(PACKAGE,version)},"")
    return selfupdate.download(release,[PACKAGE])

def install_argv(files) -> list:
    return selfupdate.install_argv(files)

def remove_argv() -> list:
    return ["env","DEBIAN_FRONTEND=noninteractive","apt-get","remove","-y",PACKAGE]
