#!/usr/bin/env bash
# Build TVWCS's Debian packages from the repository, into resources/:
#   tvwcs_<version>_all.deb             the program, its sway session and the Settings app
#   tvwcs-boot-logo_<version>_all.deb   the TVWCS logo while the computer starts (a Plymouth theme)
# Both are plain dpkg-deb builds: architecture independent, no compiling. The release workflow attaches them to the
# GitHub release, where install.sh and TVWCS's updater download them.
set -euo pipefail
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(cat "$ROOT/VERSION")
OUT=$ROOT/resources; mkdir -p "$OUT"
STAGE=$(mktemp -d); trap 'rm -rf "$STAGE"' EXIT

control() {   # control <package> <staged tree>: DEBIAN/control with the version and size filled in
    mkdir -p "$2/DEBIAN"
    SIZE=$(du -sk --exclude=DEBIAN "$2" | cut -f1)
    sed -e "s/@VERSION@/$VERSION/" -e "s/@SIZE@/$SIZE/" "$ROOT/packaging/$1/control" > "$2/DEBIAN/control"
}
build() {   # build <staged tree>: owned by root, standard permissions
    find "$1" -type d -exec chmod 755 {} +
    dpkg-deb --root-owner-group -Zxz --build "$1" "$OUT/$(basename "$1")_${VERSION}_all.deb" >/dev/null
    echo "Built resources/$(basename "$1")_${VERSION}_all.deb"
}

# ---------------------------------------------------------------------- tvwcs
P=$STAGE/tvwcs
install -d "$P/usr/lib/tvwcs/tvwcs" "$P/usr/bin" "$P/usr/share/tvwcs" "$P/usr/share/wayland-sessions" "$P/usr/share/applications" \
    "$P/usr/share/icons/hicolor/scalable/apps" "$P/usr/share/doc/tvwcs"
install -m 644 "$ROOT"/package/tvwcs/*.py "$P/usr/lib/tvwcs/tvwcs/"
install -m 644 "$ROOT/VERSION" "$P/usr/lib/tvwcs/VERSION"
install -m 755 "$ROOT/package/bin/tvwcs" "$P/usr/bin/tvwcs"
install -m 755 "$ROOT/data/tvwcs-session" "$P/usr/bin/tvwcs-session"
install -m 644 "$ROOT/data/tvwcs.conf" "$P/usr/share/tvwcs/tvwcs.conf"
install -m 644 "$ROOT/data/tvwcs-sway.desktop" "$P/usr/share/wayland-sessions/tvwcs-sway.desktop"
install -m 644 "$ROOT/data/com.tvwcs.ControlPanel.desktop" "$P/usr/share/applications/"
install -m 644 "$ROOT/data/tvwcs.svg" "$ROOT/data/tvwcs-settings.svg" "$P/usr/share/icons/hicolor/scalable/apps/"
install -m 644 "$ROOT/README.md" "$ROOT/CHANGELOG.md" "$P/usr/share/doc/tvwcs/"
install -m 644 "$ROOT/LICENSE" "$P/usr/share/doc/tvwcs/copyright"
control tvwcs "$P"
install -m 755 "$ROOT/packaging/tvwcs/postinst" "$ROOT/packaging/tvwcs/prerm" "$P/DEBIAN/"
build "$P"

# ---------------------------------------------------------------------- tvwcs-boot-logo
P=$STAGE/tvwcs-boot-logo
install -d "$P/usr/share/plymouth/themes/tvwcs" "$P/etc/default/grub.d" "$P/usr/share/doc/tvwcs-boot-logo"
install -m 644 "$ROOT"/data/plymouth/tvwcs/* "$P/usr/share/plymouth/themes/tvwcs/"
install -m 644 "$ROOT/packaging/tvwcs-boot-logo/grub.cfg" "$P/etc/default/grub.d/tvwcs-boot-logo.cfg"
install -m 644 "$ROOT/LICENSE" "$P/usr/share/doc/tvwcs-boot-logo/copyright"
control tvwcs-boot-logo "$P"
install -m 755 "$ROOT/packaging/tvwcs-boot-logo/postinst" "$ROOT/packaging/tvwcs-boot-logo/postrm" "$P/DEBIAN/"
echo /etc/default/grub.d/tvwcs-boot-logo.cfg > "$P/DEBIAN/conffiles"
build "$P"
