#!/usr/bin/env bash
# Recreate the Vast CLI environment that tools/assetgen/vast.sh depends on.
# Safe to re-run; installs nothing outside tools/assetgen/.venv.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HERE/.venv"
REQ="$HERE/requirements.txt"

if [ ! -x "$VENV/bin/python" ]; then
    echo "bootstrap: creating $VENV"
    python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r "$REQ"

if [ ! -x "$VENV/bin/vastai" ]; then
    echo "bootstrap: FAILED — $VENV/bin/vastai still missing" >&2
    exit 1
fi
echo "bootstrap: vastai $("$VENV/bin/vastai" --version 2>&1 | head -1) ready at $VENV/bin/vastai"
echo "bootstrap: credentials are read from .env (VAST_API_KEY); this script never writes them"
