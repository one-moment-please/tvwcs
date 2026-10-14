#!/usr/bin/env bash
# Build a distributable zip of TVWCS from the repository.
#   scripts/make-release.sh            -> resources/TVWCS-<version>.zip        (release build)
#   scripts/make-release.sh --beta     -> resources/TVWCS-<version>-beta.<n>.zip
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
rm -f "$ROOT/resources/$NAME.zip"   # zip -r would otherwise add to an old archive of the same name
mkdir -p "$STAGE/tvwcs/tvwcs"
cp "$ROOT"/package/tvwcs/*.py "$STAGE/tvwcs/tvwcs/"
mkdir -p "$STAGE/tvwcs/bin"; cp "$ROOT/package/bin/tvwcs" "$STAGE/tvwcs/bin/"
cp "$ROOT/data/tvwcs.conf" "$ROOT/data/com.tvwcs.ControlPanel.desktop" "$ROOT/VERSION" "$ROOT/LICENSE" "$ROOT/README.md" "$ROOT/CHANGELOG.md" "$STAGE/tvwcs/"
cp "$ROOT/scripts/install.sh" "$STAGE/tvwcs/"
if command -v zip >/dev/null 2>&1; then
    (cd "$STAGE" && zip -rq "$ROOT/resources/$NAME.zip" tvwcs)
else
    # fall back to Python's zipfile when the `zip` package is not installed
    (cd "$STAGE" && python3 -m zipfile -c "$ROOT/resources/$NAME.zip" tvwcs)
fi
echo "Built resources/$NAME.zip"
