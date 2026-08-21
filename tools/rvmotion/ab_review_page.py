"""Build the A/B review page from whatever the run actually produced.

Reads the two scorecards and renders both side by side: (A) morphology-normalised
generator quality and (B) the production result. Missing pieces are shown as
missing rather than omitted, so a partial run cannot read as a complete one.

  python3 tools/rvmotion/ab_review_page.py <out.html>
"""
import glob
import html
import json
import os
import sys

OUT = sys.argv[1]
ROOT = os.getcwd()
cards = {}
for f in sorted(glob.glob("art/animation/ab/scorecard_*.json")):
    d = json.load(open(f))
    cards[d["label"]] = d
names = list(cards) or ["kimodo", "ardy"]


def cell(label, fn):
    vals = []
    for n in names:
        try:
            v = fn(cards[n])
            vals.append("—" if v is None else str(v))
        except Exception:
            vals.append('<span class="miss">n/a</span>')
    return "<tr><td>%s</td>%s</tr>" % (
        html.escape(label), "".join("<td class='n'>%s</td>" % v for v in vals))


def vids(gen):
    out = []
    for tag in ("side", "threequarter", "gameplay"):
        p = os.path.join(ROOT, "art/animation/ab", gen, "ab_%s_%s.mp4" % (gen, tag))
        if os.path.exists(p):
            out.append("<figure><video src='file://%s' controls autoplay loop muted "
                       "playsinline></video><figcaption><b>%s %s</b></figcaption></figure>"
                       % (p, html.escape(gen), tag))
    nat = os.path.join(ROOT, "art/animation/ab", gen, "native", "native_f000.png")
    if os.path.exists(nat):
        out.append("<figure><img src='file://%s'><figcaption><b>%s native source</b>"
                   "</figcaption></figure>" % (nat, html.escape(gen)))
    return "".join(out) or "<p class='miss'>no media for %s</p>" % html.escape(gen)


doc = """<!doctype html><meta charset="utf-8"><title>Red Valley — generator A/B</title>
<style>
 :root{--bg:#15171a;--panel:#1d2024;--line:#2c3036;--ink:#e8eaed;--dim:#9aa2ac;--ok:#6fc48b;--bad:#e07a6b}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 ui-sans-serif,system-ui,sans-serif;padding:24px 28px 60px}
 h1{font-size:20px;margin:0 0 4px}.sub{color:var(--dim);font-size:13px;margin-bottom:22px}
 h2{font-size:17px;margin:30px 0 10px;padding-top:14px;border-top:1px solid var(--line)}
 table{border-collapse:collapse;width:100%;font-size:13.5px}
 th,td{text-align:left;padding:5px 10px;border-bottom:1px solid var(--line)}
 th{color:var(--dim)} td.n{font-variant-numeric:tabular-nums}
 .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:13px}
 figure{margin:0;background:var(--panel);border:1px solid var(--line);border-radius:8px;overflow:hidden}
 video,img{width:100%;display:block;background:#000}
 figcaption{padding:7px 10px;font-size:12.5px;color:var(--dim)}
 .miss{color:var(--bad)}
 p.note{color:var(--dim);font-size:13px}
</style>
<h1>Generator A/B — ARDY vs Kimodo, identical contract</h1>
<div class="sub">One rented 24 GB GPU, one seed each, post-processing on, same RVM/1 pipeline for both. Two scorecards, because skeleton size is not model quality.</div>
<h2>A — morphology-normalised generator quality</h2>
<p class="note">Measured on the <b>native</b> output in body-relative units, so skeleton size cancels. This is the fair model comparison.</p>
<table><tr><th>metric</th>%HEAD%</tr>
%A%
</table>
<h2>B — production result</h2>
<p class="note">The clip retargeted onto the Rigify character holding the <b>fixed shipping can</b>, in absolute metres. Anthropometry deliberately does <i>not</i> cancel here.</p>
<table><tr><th>metric</th>%HEAD%</tr>
%B%
</table>
<h2>Contract as issued</h2>
<table><tr><th>item</th>%HEAD%</tr>
%C%
</table>
<h2>Media</h2>
<div class="grid">%V%</div>
"""
head = "".join("<th>%s</th>" % html.escape(n) for n in names)
A = "\n".join([
    cell("trunk lean at pour (deg)", lambda d: d["A_morphology_normalised"]["trunk_lean_at_pour_deg"]["mean"]),
    cell("arm extension at pour", lambda d: d["A_morphology_normalised"]["arm_extension_at_pour"]["mean"]),
    cell("pelvis drop (hip fraction)", lambda d: d["A_morphology_normalised"]["pelvis_drop_hip_fraction"]),
    cell("lead foot advance (hip fraction)", lambda d: d["A_morphology_normalised"]["lead_foot_advance_hip_fraction"]),
    cell("rear foot drift (hip fraction)", lambda d: d["A_morphology_normalised"]["rear_foot_drift_hip_fraction"]),
    cell("took a step?", lambda d: d["A_morphology_normalised"]["gate_lead_foot_stepped"]),
    cell("rear foot stayed?", lambda d: d["A_morphology_normalised"]["gate_rear_foot_stayed"]),
    cell("arm not hyperextended?", lambda d: d["A_morphology_normalised"]["gate_arm_not_hyperextended"]),
    cell("no flight phase?", lambda d: d["A_morphology_normalised"]["gate_no_flight"]),
])
B = "\n".join([
    cell("spout window (m above bed)", lambda d: d["B_production"]["spout_window_m"]),
    cell("spout held the band?", lambda d: d["B_production"]["spout_in_band"]),
    cell("forward reach ratio", lambda d: d["B_production"]["forward_reach_ratio"]),
    cell("step events", lambda d: d["B_production"]["step_events"]),
    cell("foot skating peak (cm/s)", lambda d: d["B_production"]["foot_skating_peak_cm_s"]),
    cell("can/body collisions", lambda d: d["B_production"]["body_collisions"]),
    cell("grip-region contact", lambda d: d["B_production"]["grip_region_contact"]),
    cell("joint limits ok?", lambda d: d["B_production"]["joint_limits_ok"]),
])
C = "\n".join([
    cell("fps / frames", lambda d: "%s / %s" % (d["contract"]["fps"], d["contract"]["frames"])),
    cell("trunk lean the contract needed (deg)", lambda d: d["contract"]["min_trunk_lean_deg"]),
    cell("pelvis drop asked (m)", lambda d: d["contract"]["pelvis_drop_m"]),
    cell("spout target (documented, m)", lambda d: d["contract"]["spout_target_documented_m"]),
    cell("target escalated?", lambda d: d["contract"]["spout_target_escalated"]),
    cell("keyframes per set", lambda d: d["contract"]["constrained_frames_per_set"]),
])
doc = (doc.replace("%HEAD%", head).replace("%A%", A).replace("%B%", B)
          .replace("%C%", C).replace("%V%", "".join(vids(n) for n in names)))
open(OUT, "w").write(doc)
print("wrote", OUT, "for", names)
