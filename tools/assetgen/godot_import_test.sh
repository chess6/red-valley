#!/usr/bin/env bash
# Disposable Godot import test for one GLB: copies it into a throwaway
# project (never the real project.godot), forces an import headlessly, and
# reports whether it succeeded -- then deletes the throwaway project.
# No asset repair, no engine-side authoring.
#
#   tools/assetgen/godot_import_test.sh path/to/asset.glb
set -uo pipefail
GODOT="${GODOT_BIN:-/opt/Godot4/Godot_v4.7-stable_linux.x86_64}"
GLB="${1:?usage: godot_import_test.sh <glb-path>}"
[ -f "$GLB" ] || { echo "godot_import_test: no such file: $GLB" >&2; exit 2; }
[ -x "$GODOT" ] || { echo "godot_import_test: Godot binary not found at $GODOT" >&2; exit 2; }

TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

cat > "$TMP/project.godot" <<'EOF'
config_version=5

[application]
config/name="import_smoke_test"
EOF

cp "$GLB" "$TMP/asset.glb"

LOG="$TMP/import.log"
"$GODOT" --headless --path "$TMP" --import >"$LOG" 2>&1

if grep -qiE "ERROR|Failed to (load|import)" "$LOG"; then
	echo "godot_import_test: FAILED -- $GLB"
	grep -iE "ERROR|Failed to (load|import)" "$LOG"
	exit 1
fi
if [ ! -f "$TMP/asset.glb.import" ]; then
	echo "godot_import_test: FAILED -- no .import generated for $GLB"
	cat "$LOG"
	exit 1
fi

echo "godot_import_test: OK -- $GLB imports cleanly"
exit 0
