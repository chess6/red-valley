#!/usr/bin/env bash
# v2 animation gates. These FAIL on the v1 retargeter by construction:
#   * twist: v1 aims bones with a minimal-arc rotation, which cannot carry roll,
#     so its forearm roll range is roughly half the source's.
#   * prop socket: v1 exported with export_def_bones=True while prop_socket.R
#     was use_deform=False, so the socket is absent from the v1 GLBs.
#   * BoneAttachment3D: never tested against a v1 GLB at all.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GODOT="${GODOT_BIN:-/opt/Godot4/Godot_v4.7-stable_linux.x86_64}"
V2="$ROOT/art/animation/v2"
fail=0
say() { printf '  %-52s %s\n' "$1" "$2"; }

# ---- 1. machine-readable gates from the validation JSONs -------------------
python3 - "$V2" <<'PY'
import json, os, sys
V2 = sys.argv[1]
fails = []
def gate(name, ok, detail):
    print("  %-52s %s  (%s)" % (name, "PASS" if ok else "FAIL", detail))
    if not ok: fails.append(name)

for label, f in (("walk_fwd", "compare/v2_walk_validation.json"),
                 ("water_can", "compare/v2_water_validation.json")):
    p = os.path.join(V2, f)
    if not os.path.exists(p):
        print("  %-52s SKIP (not built)" % label); continue
    r = json.load(open(p))
    rf = r["rotation_fidelity"]
    gate("%s: rotation fidelity mean < 2 deg" % label, rf["gate_mean_lt_2deg"],
         "%.2f deg" % rf["overall_mean_deg"])
    gate("%s: no critical-bone limit breached" % label, rf["gate_no_critical_bone_breach"],
         ", ".join("%s %.1f>%.0f" % (k, v["max_deg"], v["limit_deg"])
                   for k, v in rf["per_bone_breaches"].items()) or "none")
    if rf.get("authored_override_deviation_deg"):
        print("  %-52s %s  (%s)" % ("%s: authored overrides (reported, not gated)" % label,
              "NOTE", ", ".join("%s %.1f deg" % (k, v["max"])
                                for k, v in rf["authored_override_deviation_deg"].items())))
    tw = r.get("twist_channel", {})
    live = [k for k, v in tw.items() if v["range_deg"] > 5.0]
    gate("%s: twist bones carry signal" % label, len(live) >= 2,
         "%d of %d channels > 5 deg" % (len(live), len(tw)))
    if "foot_contacts" in r and r["foot_contacts"]["per_foot"]:
        fc = r["foot_contacts"]
        gate("%s: foot skating peak < 5 cm/s" % label, fc["gate_peak_slide_lt_5cm_s"],
             ", ".join("%s %.2f" % (k, v["peak_slide_cm_per_s"]) for k, v in fc["per_foot"].items()))
    if "loop_seam" in r:
        ls = r["loop_seam"]
        gate("%s: loop seam <= interior median (proposed)" % label,
             ls["gate_proposed_seam_below_interior_median"],
             "seam %.4f m vs interior median %.4f m, %d contact flip(s) at wrap "
             "vs %d inside" % (ls["seam_extrapolation_err_m"], ls["interior_err_median_m"],
                               ls["contact_channel_flips_at_wrap"],
                               ls["max_contact_flips_inside_cycle"]))
    if "prop_rigidity" in r:
        gate("%s: prop rigid to the hand" % label, r["prop_rigidity"]["gate_rigid"],
             "%.2e m drift" % r["prop_rigidity"]["max_hand_relative_drift_m"])
        gate("%s: zero can/body collisions" % label, r["collisions"]["gate_zero"],
             "%d tris" % r["collisions"]["max_tris"])
        sp = r["spout"]
        gate("%s: spout in documented band" % label, sp["gate_in_band"],
             "%.3f-%.3f m above bed, band %s" % (sp["min_above_bed_m"], sp["max_above_bed_m"],
                                                 sp["documented_band_m"]))
    fa = r["face"]
    gate("%s: face core rigid < 0.5%%" % label, fa["gate_core_rigid_lt_0p5pct"],
         "%.3f%%" % fa["core_worst_strain_pct"])
    gate("%s: jaw/neck blend band < 25%%" % label, fa["gate_band_lt_25pct"],
         "%.2f%%" % fa["band_worst_strain_pct"])

t = os.path.join(V2, "compare/water_timing.json")
if os.path.exists(t):
    r = json.load(open(t))
    gate("water_can: one-shot ~1.2 s", abs(r["output_duration_s"] - 1.2) < 0.1,
         "%.2f s" % r["output_duration_s"])
    gate("water_can: sync point ~0.45 s", abs(r["sync"]["output_time_s"] - 0.45) < 0.05,
         "%.2f s" % r["sync"]["output_time_s"])
    gate("water_can: time compression <= 2.5x", r["time_compression"] <= 2.5,
         "%.2fx" % r["time_compression"])
sys.exit(1 if fails else 0)
PY
[ $? -ne 0 ] && fail=1

# ---- 2. Godot round-trip, including a real BoneAttachment3D ----------------
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
printf 'config_version=5\n\n[application]\nconfig/name="v2"\nconfig/features=PackedStringArray("4.4")\n' > "$T/project.godot"
n=0
for c in walk_fwd water_can; do
  [ -f "$V2/$c/$c.glb" ] && { cp "$V2/$c/$c.glb" "$T/"; n=$((n+1)); }
done
if [ "$n" = 0 ]; then say "godot round-trip" "SKIP (no GLBs)"; exit "$fail"; fi
"$GODOT" --headless --editor --quit --path "$T" >/dev/null 2>&1
cat > "$T/check.gd" <<'GD'
extends SceneTree

func settle(n: int) -> void:
    # BoneAttachment3D updates on skeleton notifications during processing, so a
    # bare seek() leaves its transform stale. Step real process frames instead of
    # reading the bone chain by hand -- that proved the BONE moves, not that an
    # attached prop follows it.
    for i in n:
        await process_frame

func bone_global(sk: Skeleton3D, idx: int) -> Transform3D:
    var t := Transform3D()
    var i := idx
    while i >= 0:
        t = (sk.get_bone_rest(i) * Transform3D(Basis(sk.get_bone_pose_rotation(i)).scaled(
                sk.get_bone_pose_scale(i)), sk.get_bone_pose_position(i))) * t
        i = sk.get_bone_parent(i)
    return t

func _init():
    run_all()

func run_all() -> void:
    var fails := 0
    for spec in [["walk_fwd", 1.0, false], ["water_can", 1.2, true]]:
        var nm: String = spec[0]
        if not ResourceLoader.exists("res://%s.glb" % nm): continue
        var s = load("res://%s.glb" % nm)
        if s == null:
            print("  FAIL ", nm, ": did not load"); fails += 1; continue
        var n = s.instantiate()
        get_root().add_child(n)
        var sk: Skeleton3D = n.find_child("Skeleton3D", true, false)
        var ap: AnimationPlayer = n.find_child("AnimationPlayer", true, false)
        var anims := ap.get_animation_list()
        var len_ok: bool = absf(ap.get_animation(anims[0]).length - float(spec[1])) < 0.08
        var nondef := 0
        for i in sk.get_bone_count():
            if not sk.get_bone_name(i).begins_with("DEF-"): nondef += 1
        var ok: bool = anims.size() == 1 and String(anims[0]) == nm and len_ok and nondef == 0
        var attach_ok := true
        if bool(spec[2]):
            # the prop contract must be targetable by name from Godot
            var bi := sk.find_bone("DEF-prop_socket.R")
            attach_ok = bi >= 0
            if attach_ok:
                var ba := BoneAttachment3D.new()
                ba.bone_name = "DEF-prop_socket.R"
                sk.add_child(ba)
                var parent_name := sk.get_bone_name(sk.get_bone_parent(bi))
                ap.play(anims[0])
                # Skeleton3D.get_bone_global_pose() is stale in a SceneTree script
                # (it is refreshed during processing, and there are no process
                # ticks here), so chain rest*pose up the hierarchy by hand. This
                # is what BoneAttachment3D reads at runtime.
                ap.seek(0.0, true)
                await settle(3)
                var a := ba.global_transform
                ap.seek(0.45, true)
                await settle(3)
                var b := ba.global_transform
                var d := a.origin.distance_to(b.origin)
                var ang := a.basis.get_rotation_quaternion().angle_to(
                    b.basis.get_rotation_quaternion())
                # cross-check against the hand-computed chain: if these disagree
                # the attachment is not tracking what we think it is
                # In-engine rigidity: a second attachment on DEF-hand.R. If the
                # prop contract holds, the socket's transform RELATIVE to the hand
                # is constant for the whole clip. Comparing against a hand-rolled
                # bone-chain walk instead just tested my own arithmetic.
                var bh := BoneAttachment3D.new()
                bh.bone_name = "DEF-hand.R"
                sk.add_child(bh)
                var rel_max := 0.0
                var rel0 := Transform3D()
                var first := true
                for i in 13:
                    ap.seek(1.2 * float(i) / 12.0, true)
                    await settle(2)
                    var rel: Transform3D = bh.global_transform.affine_inverse() * ba.global_transform
                    if first:
                        rel0 = rel; first = false
                    else:
                        rel_max = maxf(rel_max, rel0.origin.distance_to(rel.origin))
                print("  attachment rigidity vs DEF-hand.R over the clip: ",
                      "%.6f" % rel_max, " m")
                var gap := rel_max
                attach_ok = (d > 0.01 or ang > 0.05) and parent_name == "DEF-hand.R" and gap < 0.001
                print("  BoneAttachment3D target DEF-prop_socket.R (parent ",
                      parent_name, ") moved ", "%.3f" % d, " m / ",
                      "%.1f" % rad_to_deg(ang), " deg over the descent")
        print(("  PASS " if (ok and attach_ok) else "  FAIL "), nm,
              " bones=", sk.get_bone_count(), " nondef=", nondef,
              " anims=", anims, " len=", ap.get_animation(anims[0]).length,
              " attach=", attach_ok)
        if not (ok and attach_ok): fails += 1
    quit(1 if fails > 0 else 0)
GD
"$GODOT" --headless --path "$T" --script "$T/check.gd" 2>/dev/null | grep -E '^  (PASS|FAIL|BoneAttachment|attachment)'
[ "${PIPESTATUS[0]}" -ne 0 ] && fail=1
exit "$fail"
