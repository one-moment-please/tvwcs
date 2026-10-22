#!/bin/sh
# Run all display-free unit tests (model, hotkey logic, window-manager parsing).
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec python3 -m unittest discover -s "$ROOT/package/tests" -t "$ROOT/package" -v
