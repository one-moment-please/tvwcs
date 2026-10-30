#!/usr/bin/env bash
# Build TVWCS's Arch package files from the repository, into resources/arch/:
#   tvwcs-<version>-src.tar.gz   the source: the repository's files, without the demo videos and old releases
#   PKGBUILD, tvwcs.install      from packaging/arch/, with the version and the tarball's checksum filled in: ready
#                                to build with makepkg, or to send to the AUR
#   .SRCINFO                     what the AUR reads; only where makepkg is installed (on Arch)
# The release workflow attaches the first three to the GitHub release. On Arch,
#   scripts/build-arch.sh --package   also builds the package (makepkg, not as root): tvwcs-<version>-1-any.pkg.tar.zst;
#                                     pacman -U then installs it with what it needs
# makepkg finds the tarball next to the PKGBUILD, so this builds from the checkout without downloading anything.
set -euo pipefail
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(cat "$ROOT/VERSION")
OUT=$ROOT/resources/arch
NAME=tvwcs-$VERSION
rm -rf "$OUT"; mkdir -p "$OUT"
( cd "$ROOT" && git ls-files -z --cached --others --exclude-standard -- . ':!assets' ':!resources' |
  tar --null -T - --transform "s,^,$NAME/," --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - ) |
  gzip -n9 > "$OUT/$NAME-src.tar.gz"
SUM=$(sha256sum "$OUT/$NAME-src.tar.gz" | cut -d' ' -f1)
sed -e "s/@VERSION@/$VERSION/" -e "s/@SHA256@/$SUM/" "$ROOT/packaging/arch/PKGBUILD.in" > "$OUT/PKGBUILD"
cp "$ROOT/packaging/arch/tvwcs.install" "$OUT/"
echo "Built resources/arch/PKGBUILD, tvwcs.install and $NAME-src.tar.gz"
if command -v makepkg >/dev/null 2>&1; then
    (cd "$OUT" && makepkg --printsrcinfo > .SRCINFO) && echo "Built resources/arch/.SRCINFO"
    if [ "${1:-}" = --package ]; then
        (cd "$OUT" && makepkg -f --nodeps --noconfirm) && echo "Built resources/arch/$(cd "$OUT" && ls ./*.pkg.tar.*)"
    fi
elif [ "${1:-}" = --package ]; then
    echo "makepkg is not installed: building the package needs Arch." >&2; exit 1
fi
