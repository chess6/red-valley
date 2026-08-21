"""Show that the v2 gates actually fail on the v1 retargeter.

A test that only passes on the new code proves nothing about the old code; this
runs the same measurements against the committed v1 artefacts.
"""
import json, os, struct, sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "art/animation/v2/compare/v1_gate_proof.json"
res = {}

# gate: prop socket present in the exported GLB
def glb(p):
    d = open(p, "rb").read(); off = 12; js = None
    while off < len(d):
        clen, ctype = struct.unpack("<II", d[off:off + 8]); off += 8
        if ctype == 0x4E4F534A: js = json.loads(d[off:off + clen])
        off += clen
    return js
socket = {}
for tag, p in (("v1", "art/animation/rigify/water_can/water_can.glb"),
               ("v2", "art/animation/v2/water_can/water_can.glb")):
    if not os.path.exists(p): continue
    js = glb(p)
    jn = [js["nodes"][i].get("name", "") for i in js["skins"][0]["joints"]]
    socket[tag] = {"joints": len(jn), "prop_socket_present": any("prop_socket" in n for n in jn)}
res["gate_prop_socket_in_glb"] = {"per_version": socket,
                                  "v1_fails": not socket.get("v1", {}).get("prop_socket_present", False),
                                  "v2_passes": socket.get("v2", {}).get("prop_socket_present", False)}

# gate: twist preserved (measured earlier against the same canonical source)
v1 = json.load(open("art/animation/v2/compare/v1_water.json"))
v2 = json.load(open("art/animation/v2/compare/v2_water.json"))
tw = {}
for s in ("R", "L"):
    a, b = v1["forearm_roll_range_deg"][s], v2["forearm_roll_range_deg"][s]
    tw[s] = {"source_deg": a["source_deg"], "v1_deg": a["target_deg"], "v2_deg": b["target_deg"],
             "v1_loss_pct": round(100 * (1 - a["target_deg"] / a["source_deg"]), 1),
             "v2_loss_pct": round(100 * (1 - b["target_deg"] / b["source_deg"]), 1)}
res["gate_twist_preserved"] = {"per_side": tw,
                               "v1_fails": any(v["v1_loss_pct"] > 5 for v in tw.values()),
                               "v2_passes": all(v["v2_loss_pct"] <= 5 for v in tw.values())}
res["gate_rotation_fidelity"] = {
    "v1_mean_deg": v1["mean_delta_err_deg"], "v2_mean_deg": v2["mean_delta_err_deg"],
    "threshold_deg": 1.0,
    "v1_fails": v1["mean_delta_err_deg"] > 1.0, "v2_passes": v2["mean_delta_err_deg"] <= 1.0}

# gate: documented one-shot timing
prov = json.load(open("art/animation/rigify/CLIPS_PROVENANCE.json"))
t = json.load(open("art/animation/v2/compare/water_timing.json"))
res["gate_oneshot_timing"] = {"documented_s": 1.2,
                              "v1_s": prov["clips"]["water_can"]["duration_s"],
                              "v2_s": t["output_duration_s"],
                              "v1_fails": abs(prov["clips"]["water_can"]["duration_s"] - 1.2) > 0.1,
                              "v2_passes": abs(t["output_duration_s"] - 1.2) <= 0.1}
json.dump(res, open(OUT, "w"), indent=2)
for k, v in res.items():
    print("  %-28s v1 fails: %-5s   v2 passes: %-5s" % (k, v["v1_fails"], v["v2_passes"]))
