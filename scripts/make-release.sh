#!/usr/bin/env bash
# Build a distributable zip of TVWCS from the repository.
#   scripts/make-release.sh            -> resources/TVWCS-<version>.zip        (release build)
#   scripts/make-release.sh --beta     -> resources/TVWCS-<version>-beta.<n>.zip
# Both also build resources/tvwcs.tar.gz with the same contents. Its name never changes, so the README's install
# command can download it from https://github.com/one-moment-please/tvwcs/releases/latest/download/tvwcs.tar.gz.
set -euo pipefail
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(cat "$ROOT/VERSION")
SUFFIX=""
if [ "${1:-}" = "--beta" ]; then
    N=$(git -C "$ROOT" tag -l "v$VERSION-beta*" 2>/dev/null | wc -l | tr -d ' ')
    SUFFIX="-beta.$((N+1))"
fi
NAME="TVWCS-${VERSION}${SUFFIX}"
STAGE=$(mktemp -d); trap 'rm -rf "$STAGE"' EXIT
rm -f "$ROOT/resources/$NAME.zip" "$ROOT/resources/tvwcs.tar.gz"   # zip -r would otherwise add to an old archive
mkdir -p "$STAGE/tvwcs/tvwcs"
cp "$ROOT"/package/tvwcs/*.py "$STAGE/tvwcs/tvwcs/"
mkdir -p "$STAGE/tvwcs/bin"; cp "$ROOT/package/bin/tvwcs" "$STAGE/tvwcs/bin/"
cp "$ROOT/data/tvwcs.conf" "$ROOT/data/com.tvwcs.ControlPanel.desktop" "$ROOT/data/tvwcs-settings.svg" "$ROOT/VERSION" "$ROOT/LICENSE" "$ROOT/README.md" "$ROOT/CHANGELOG.md" "$ROOT/TODO.md" "$STAGE/tvwcs/"
cp "$ROOT/scripts/install.sh" "$STAGE/tvwcs/"
if command -v zip >/dev/null 2>&1; then
    (cd "$STAGE" && zip -rq "$ROOT/resources/$NAME.zip" tvwcs)
else
    # fall back to Python's zipfile when the `zip` package is not installed
    (cd "$STAGE" && python3 -m zipfile -c "$ROOT/resources/$NAME.zip" tvwcs)
fi
tar -czf "$ROOT/resources/tvwcs.tar.gz" -C "$STAGE" tvwcs
echo "Built resources/$NAME.zip and resources/tvwcs.tar.gz"
