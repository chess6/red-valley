#!/usr/bin/env bash
# Full verification: unit tests + integration test, headless. Run this
# before claiming any task complete (see CLAUDE.md). Exits nonzero if
# either suite fails.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

GODOT="${GODOT_BIN:-/opt/Godot4/Godot_v4.7-stable_linux.x86_64}"

if [[ ! -x "$GODOT" ]]; then
	echo "verify: Godot binary not found/executable at $GODOT" >&2
	echo "        set GODOT_BIN to override, or see docs/SETUP.md" >&2
	exit 1
fi

# Running Godot at all (even --headless --script) can silently rewrite
# project.godot. Snapshot the file's exact current bytes so we can put them
# back afterward.
#
# Deliberately a byte-for-byte copy rather than `git checkout --
# project.godot`: checkout would reset to HEAD and thereby destroy any
# INTENTIONAL uncommitted edits the caller happens to have in the file.
# This restores what was there when verify started, committed or not, and
# works outside a git tree too.
snapshot=""
if [[ -f project.godot ]]; then
	snapshot="$(mktemp)"
	cp -p project.godot "$snapshot"
	# shellcheck disable=SC2064  # intentional: expand $snapshot now, not at trap time
	trap "rm -f '$snapshot'" EXIT
fi

overall=0

# First, because it needs no Godot and catches the expensive-to-discover-late
# class of problem: an asset with no provenance, or evaluation-only output
# leaking toward a build.
echo "== commercial-asset gate (tools/asset_gate.py) =="
if ! python3 tools/asset_gate.py check; then
	echo "verify: asset gate FAILED" >&2
	overall=1
fi
if ! python3 tools/tests/test_asset_gate.py >/dev/null 2>&1; then
	echo "verify: asset gate self-tests FAILED -- rerun 'python3 tools/tests/test_asset_gate.py' for detail" >&2
	overall=1
fi

echo
echo "== unit tests (tests/run_tests.gd) =="
if ! "$GODOT" --headless --path . --script tests/run_tests.gd; then
	echo "verify: unit tests FAILED" >&2
	overall=1
fi

echo
echo "== integration test (tests/integration.tscn) =="
if ! "$GODOT" --headless --path . res://tests/integration.tscn; then
	echo "verify: integration test FAILED" >&2
	overall=1
fi

if [[ -n "$snapshot" ]] && ! cmp -s project.godot "$snapshot"; then
	echo
	echo "verify: Godot rewrote project.godot during this run -- restoring it to" >&2
	echo "        exactly what it was before verify started." >&2
	cp -p "$snapshot" project.godot
fi

echo
if [[ "$overall" -eq 0 ]]; then
	echo "verify: ALL PASSED"
else
	echo "verify: FAILED -- see above"
fi
exit "$overall"
