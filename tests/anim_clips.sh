#!/usr/bin/env bash
# Playback test for the animation-pipeline clips (walk_fwd, water_can).
#
# The clips live under art/ (Godot-ignored via art/.gdignore), so this builds a
# disposable scratch project, imports each GLB there, and asserts: deform-only
# skeleton, exactly one animation with the expected name and duration, and that
# playback actually moves bones. Skips cleanly if the clips are absent (fresh
# clone without the animation deliverables).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GODOT="${GODOT_BIN:-/opt/Godot4/Godot_v4.7-stable_linux.x86_64}"
CLIPS=(
  "art/animation/rigify/walk_fwd/walk_fwd.glb:walk_fwd:1.0"
  "art/animation/rigify/water_can/water_can.glb:water_can:8.0"
)
missing=0
for spec in "${CLIPS[@]}"; do
  [ -f "$ROOT/${spec%%:*}" ] || missing=1
done
if [ "$missing" = 1 ]; then
  echo "anim_clips: clips not present — skipping (regenerate via tools/ardy)"
  exit 0
fi
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
printf 'config_version=5\n\n[application]\nconfig/name="anim_clips_test"\nconfig/features=PackedStringArray("4.4")\n' > "$T/project.godot"
for spec in "${CLIPS[@]}"; do
  cp "$ROOT/${spec%%:*}" "$T/"
done
"$GODOT" --headless --editor --quit --path "$T" >/dev/null 2>&1
cat > "$T/check.gd" <<'GD'
extends SceneTree
func _init():
    var specs := [["walk_fwd", 1.0], ["water_can", 8.0]]
    var fails := 0
    for spec in specs:
        var name: String = spec[0]
        var want_len: float = spec[1]
        var s = load("res://%s.glb" % name)
        if s == null:
            print("FAIL ", name, ": did not load"); fails += 1; continue
        var n = s.instantiate()
        var sk: Skeleton3D = n.find_child("Skeleton3D", true, false)
        var nondef := 0
        for i in sk.get_bone_count():
            if not sk.get_bone_name(i).begins_with("DEF-"): nondef += 1
        var ap: AnimationPlayer = n.find_child("AnimationPlayer", true, false)
        var anims := ap.get_animation_list()
        var ok := sk.get_bone_count() == 71 and nondef == 0 \
            and anims.size() == 1 and String(anims[0]) == name \
            and absf(ap.get_animation(anims[0]).length - want_len) < 0.06
        # playback actually moves bones
        get_root().add_child(n)
        ap.play(anims[0])
        var probe := sk.find_bone("DEF-upper_arm.R")
        ap.seek(0.0, true)
        var p0: Quaternion = sk.get_bone_pose_rotation(probe)
        ap.seek(want_len * 0.45, true)
        var p1: Quaternion = sk.get_bone_pose_rotation(probe)
        var moved := p0.angle_to(p1) > 0.02
        print(("PASS " if (ok and moved) else "FAIL "), name,
              "  bones=", sk.get_bone_count(), " nondef=", nondef,
              " anims=", anims, " len=", ap.get_animation(anims[0]).length,
              " moved=", "%.3f" % p0.angle_to(p1))
        if not (ok and moved): fails += 1
    quit(1 if fails > 0 else 0)
GD
"$GODOT" --headless --path "$T" --script "$T/check.gd" 2>/dev/null | grep -E '^(PASS|FAIL)'
exit "${PIPESTATUS[0]}"
