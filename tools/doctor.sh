#!/usr/bin/env bash
# Environment sanity check for Red Valley. Run at the start of a session,
# or whenever something in the toolchain seems off. Does not modify
# anything or run the test suites (see tools/verify.sh for that).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

GODOT="${GODOT_BIN:-/opt/Godot4/Godot_v4.7-stable_linux.x86_64}"
BLENDER="${BLENDER_BIN:-/opt/blender/blender}"

fail=0
ok()   { printf '  [ok]   %s\n' "$1"; }
warn() { printf '  [warn] %s\n' "$1"; }
bad()  { printf '  [FAIL] %s\n' "$1"; fail=1; }

echo "== Godot =="
if [[ -x "$GODOT" ]]; then
	ver="$("$GODOT" --version 2>/dev/null | head -1)"
	if [[ "$ver" == *"4.7"* ]]; then
		ok "found $GODOT ($ver)"
	else
		warn "found $GODOT but version is '$ver', expected 4.7.x"
	fi
else
	bad "Godot binary not found/executable at $GODOT (set GODOT_BIN to override; see docs/SETUP.md)"
fi

echo "== Blender =="
if [[ -x "$BLENDER" ]]; then
	ver="$("$BLENDER" --version 2>/dev/null | head -1)"
	if [[ "$ver" == *"5.1"* ]]; then
		ok "found $BLENDER ($ver)"
	else
		warn "found $BLENDER but version is '$ver', expected 5.1.x"
	fi
else
	bad "Blender binary not found/executable at $BLENDER (set BLENDER_BIN to override; see docs/SETUP.md)"
fi

echo "== Project files =="
for f in project.godot tests/run_tests.gd tests/integration.tscn tools/blender/gen_assets.py; do
	if [[ -f "$f" ]]; then
		ok "$f present"
	else
		bad "$f missing"
	fi
done

echo "== Generated assets =="
model_count="$(find assets/models -maxdepth 1 -name '*.glb' 2>/dev/null | wc -l | tr -d ' ')"
if [[ "${model_count:-0}" -gt 0 ]]; then
	ok "$model_count .glb files in assets/models/"
else
	warn "no .glb files found in assets/models/ -- run the Blender generator (docs/SETUP.md)"
fi

echo "== MCP config =="
if [[ -f .mcp.json ]]; then
	ok ".mcp.json present (run /mcp inside a Claude Code session to confirm it's connected)"
else
	warn ".mcp.json missing -- Blender MCP not configured (optional; see docs/SETUP.md)"
fi

echo "== Working tree =="
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
	if git diff --quiet -- project.godot 2>/dev/null; then
		ok "project.godot matches HEAD"
	else
		warn "project.godot has uncommitted changes -- likely the known Godot rewrite quirk (see CLAUDE.md); check with 'git diff project.godot'"
	fi
else
	warn "not inside a git working tree"
fi

echo
if [[ "$fail" -eq 0 ]]; then
	echo "doctor: environment looks OK."
else
	echo "doctor: one or more required checks FAILED (see above)."
fi
exit "$fail"
