#!/usr/bin/env bash
# Local/CI sanity build of the PyInstaller spec on Linux.
# The Windows production path is build/build_windows.ps1 + installer/mustacom.iss;
# this script proves the spec freezes cleanly and the frozen binary boots.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> installing build dependencies"
python3 -m pip install --quiet -r requirements.txt pyinstaller

echo "==> freezing (onedir)"
python3 -m PyInstaller --noconfirm build/mustacom.spec

BINARY=dist/mustacom/MUSTACOM-Business-Manager
test -x "$BINARY"
echo "==> frozen binary present: $BINARY"

echo "==> boot check (expect 'MUSTACOM BUSINESS MANAGER 1.0.0')"
"$BINARY" --version

echo "==> GUI smoke boot (killed after 12 s; a crash would exit early with != 124)"
set +e
QT_QPA_PLATFORM=offscreen MUSTACOM_DATA_DIR="${TMPDIR:-/tmp}/mustacom-frozen" \
    timeout 12 "$BINARY" --skip-license
CODE=$?
set -e
if [ "$CODE" -ne 124 ] && [ "$CODE" -ne 0 ]; then
    echo "FROZEN BINARY FAILED TO BOOT (exit $CODE)"
    exit 1
fi
echo "==> LINUX CHECK OK (exit $CODE)"
