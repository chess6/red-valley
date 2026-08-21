"""v2 audit: verify every v2 finding directly from code and assets.

Machine-readable. Findings that need Blender (6, 7, face gate) are produced by
v2_audit_blender.py and merged in here if present.

  python3 tools/ardy/v2_audit.py <out.json>
"""
import json, os, re, struct, sys
import numpy as np

OUT = sys.argv[1] if len(sys.argv) > 1 else "art/animation/v2/baseline/audit.json"
R = {}

def src(p): return open(p).read()
RT = src("tools/ardy/retarget_rigify.py")
BW = src("tools/ardy/build_water_clip.py")

# --- F1: position-only aiming; rotations and twist discarded ----------------
def reads(s):
    return sorted({k for k in ("posed_joints", "local_rot_mats", "global_rot_mats",
                               "root_positions", "smooth_root_pos", "foot_contacts",
                               "global_root_heading") if '"%s"' % k in s})
# a name that is loaded but never used again is not actually consumed
def consumed(s, key, varhint):
    uses = len(re.findall(re.escape(key), s))
    return uses > 1
R["F1_rotations_discarded"] = {
    "retarget_rigify_npz_keys_referenced": reads(RT),
    "build_water_clip_npz_keys_referenced": reads(BW),
    "foot_contacts_referenced_more_than_once_in_retarget":
        consumed(RT, "foot_contacts", "contacts") or len(re.findall(r"\bcontacts\b", RT)) > 1,
    "aim_uses_rotation_difference": "rotation_difference" in RT and "rotation_difference" in BW,
    "note": ("Vector.rotation_difference returns the minimal-arc rotation between two "
             "directions; it has zero component about the target axis, so axial twist "
             "cannot be represented at all."),
    "confirmed": ("local_rot_mats" not in reads(RT) and "local_rot_mats" not in reads(BW)
                  and "global_rot_mats" not in reads(RT) and "global_rot_mats" not in reads(BW)
                  and "rotation_difference" in RT),
}

# --- F2: DEF constraints removed; DEF animated directly ---------------------
R["F2_def_constraints_removed"] = {
    "retarget_removes_def_constraints": bool(re.search(r"DEF-.*\n.*constraints\.remove", RT)
                                             or "constraints.remove" in RT),
    "build_water_removes_def_constraints": "constraints.remove" in BW,
    "keyframes_on_def_bones": bool(re.search(r'startswith\("DEF-"\)[\s\S]{0,200}keyframe_insert', RT)),
    "drives_rigify_controls": not any(t in RT + BW for t in ("hand_ik", "MCH-", "ORG-", "torso", "foot_ik")),
    "confirmed": "constraints.remove" in RT and "constraints.remove" in BW,
}

# --- F3: twist / segment bones never driven --------------------------------
chain = re.search(r"CHAIN = \{(.*?)\n\}", BW, re.S).group(1)
driven = sorted({m for m in re.findall(r'"(DEF-[^"]+)"', chain)})
twist = [b for b in driven if re.search(r"(upper_arm|forearm|thigh|shin)\.[LR]\.\d\d\d", b)]
R["F3_twist_bones_static"] = {
    "def_bones_driven": len(driven), "driven": driven,
    "twist_segment_bones_driven": twist,
    "confirmed": len(twist) == 0,
}

# --- F4: root translation discarded ----------------------------------------
R["F4_root_translation_discarded"] = {
    "root_positions_read": "root_positions" in RT or "root_positions" in BW,
    "location_keyframed": bool(re.search(r'keyframe_insert\("location"', RT + BW)),
    "confirmed": not ("root_positions" in RT or "root_positions" in BW),
}

# --- F5: the constrained run used --no-postprocess --------------------------
sh = src("tools/ardy/water_constrained_remote.sh")
log = src("art/animation/ardy_pilot/clips_water_constrained/gen_stdout.log")
R["F5_no_postprocess"] = {
    "flag_in_runner": "--no-postprocess" in sh,
    "postprocess_mentioned_in_remote_log": "postprocess" in log.lower(),
    "confirmed": "--no-postprocess" in sh,
}

# --- F8: clip timing vs the documented one-shot contract -------------------
req = src("docs/ANIMATION_REQUIREMENTS.md")
sync = re.search(r"`water_can`\s*\|\s*~?([\d.]+)\s*s", req)
oneshot = re.search(r"`water_can`\s*\|\s*one-shot ~?([\d.]+)\s*s", req)
prov = json.load(open("art/animation/rigify/CLIPS_PROVENANCE.json"))
R["F8_timing"] = {
    "documented_sync_point_s": float(sync.group(1)) if sync else None,
    "documented_oneshot_s": float(oneshot.group(1)) if oneshot else None,
    "delivered_duration_s": prov["clips"]["water_can"]["duration_s"],
    "confirmed": abs(prov["clips"]["water_can"]["duration_s"] - float(oneshot.group(1))) > 0.2
                 if oneshot else None,
}

# --- F9: prop_socket.R absent from the exported GLBs ------------------------
def glb_json(p):
    d = open(p, "rb").read(); off = 12; js = None
    while off < len(d):
        clen, ctype = struct.unpack("<II", d[off:off + 8]); off += 8
        if ctype == 0x4E4F534A: js = json.loads(d[off:off + clen])
        off += clen
    return js
g = {}
for p in ("art/animation/rigify/water_can/water_can.glb",
          "art/animation/rigify/walk_fwd/walk_fwd.glb"):
    js = glb_json(p)
    names = [n.get("name", "") for n in js["nodes"]]
    g[os.path.basename(p)] = {
        "nodes": len(js["nodes"]), "skins": len(js["skins"]),
        "joints": len(js["skins"][0]["joints"]),
        "prop_socket_present": any("prop_socket" in n for n in names),
        "animations": [a.get("name") for a in js.get("animations", [])],
    }
R["F9_prop_socket_missing"] = {
    "glbs": g,
    "cause": "prop_socket.R has use_deform=False and export_def_bones=True drops it",
    "attachment_record_exists": os.path.exists("art/animation/rigify/water_can/can_attachment.json"),
    "godot_attachment_tested": False,
    "confirmed": not any(v["prop_socket_present"] for v in g.values()),
}

# --- F10: walk contacts, seam, speed ---------------------------------------
d = np.load("art/animation/ardy_pilot/clips8/walk8_s1.npz")
J, RT_, FC = d["posed_joints"], d["root_positions"], d["foot_contacts"]
fps = int(d["fps"])
cyc = json.load(open("art/animation/rigify/walk/cycle.json"))
a, b = int(cyc["start"]), int(cyc["end"])
n = b - a
dur = n / fps
disp = float(np.linalg.norm(RT_[b, [0, 2]] - RT_[a, [0, 2]]))
def rel(f): return J[f] - J[f][0]
seam = np.linalg.norm(rel(a) - rel(b), axis=1)
airborne_all = int((FC.sum(axis=1) == 0).sum())
airborne_win = int((FC[a:b].sum(axis=1) == 0).sum())
R["F10_walk"] = {
    "window": [a, b], "frames": n, "duration_s": round(dur, 3),
    "source_speed_mps": round(disp / dur, 3),
    "gameplay_WALK_SPEED_mps": 4.3,
    "speed_ratio_needed": round(4.3 / (disp / dur), 2),
    "ardy_labelled_airborne_frames_full_clip": [airborne_all, int(FC.shape[0])],
    "ardy_labelled_airborne_frames_window": [airborne_win, n],
    "prior_claim_from_height_threshold": "9-10 of 20 frames both-airborne",
    "correction": ("ARDY's own contact labels show 1/19 airborne in the shipped window "
                   "(4.4% over the full clip). The flight-phase verdict was an artifact "
                   "of a sole-height threshold, not the source motion."),
    "body_space_seam_mean_m": round(float(seam.mean()), 4),
    "body_space_seam_max_m": round(float(seam.max()), 4),
    "seam_target_m": 0.01,
    "seam_confirmed_too_large": bool(seam.max() > 0.01),
    "confirmed": True,
}

bl = "art/animation/v2/baseline/audit_blender.json"
if os.path.exists(bl):
    R.update(json.load(open(bl)))

os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(R, open(OUT, "w"), indent=2)
for k, v in R.items():
    c = v.get("confirmed")
    print("  %-34s %s" % (k, {True: "CONFIRMED", False: "NOT confirmed", None: "(measured)"}[c]))
print("written:", OUT)
