"""Align the Rigify human metarig to the accepted character. Iteration 1.

Body bones are taken from the accepted rv_rig's own bone positions, which are
already reviewed and approved. Finger joints come from the committed orthographic
plates: the axial plate (looking down the finger axis) separates all five digits,
so identity is read geometrically rather than assumed or taken from weights.

  blender --background --python align_metarig.py -- <src.glb> <out.blend>
"""
import json, math, os, sys
import bpy, addon_utils
from mathutils import Vector, Matrix

def _enable_rigify():
    for m in addon_utils.modules():
        if "rigify" in m.__name__.lower():
            try: addon_utils.enable(m.__name__, default_set=False)
            except Exception as e: print("rigify enable note:", e)
_enable_rigify()

argv = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = argv[0], argv[1]
MAP = json.load(open("art/animation/rigify/hand_ortho_mapping.json"))

# ---- digit readings, in millimetres in the hand frame (bar, nrm, fing) -------
# Read off hand_axial_depth_grid.png (bar/nrm and, by colour, fing) cross-checked
# against hand_palm_depth_grid.png for the fing extent. Five separated lobes, so
# identity is geometric. Bar spacing is genuinely uneven (15/19/27 mm) -- the
# index is abducted -- and the monotonic nrm rise (+7,+16,+22,+28) confirms the
# ordering pinky -> ring -> middle -> index.
DIGITS = {
    "f_pinky":  dict(base=(-56, -14, -26), tip=(-53, +12,  +4)),
    "f_ring":   dict(base=(-43, -10, -20), tip=(-39, +16, +30)),
    "f_middle": dict(base=(-22, -2, -10), tip=(-20, +22, +41)),
    "f_index":  dict(base=( +2,  0, -10), tip=( +7, +28, +40)),
    "thumb":    dict(base=(+20, +20, -38), tip=(+34, +42, -14)),
}
# The digits are curled: the path leaves the knuckle along +fing before turning
# toward +nrm, so the mid-chain sits at higher fing and lower nrm than the chord.
CURL_FING, CURL_NRM = 0.012, -0.010
THUMB_CURL_FING, THUMB_CURL_NRM = 0.004, -0.004

bpy.ops.wm.read_factory_settings(use_empty=True)
_enable_rigify()

bpy.ops.import_scene.gltf(filepath=SRC)
src_rig = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
mesh = max([o for o in bpy.data.objects if o.type == "MESH" and len(o.vertex_groups)],
           key=lambda o: len(o.data.vertices))
for o in list(bpy.data.objects):
    if o.type == "MESH" and o is not mesh:
        bpy.data.objects.remove(o, do_unlink=True)

SB = {b.name: (src_rig.matrix_world @ b.matrix_local) for b in src_rig.data.bones}
def head(n): return SB[n].to_translation()
def tail(n):
    b = src_rig.data.bones[n]
    return src_rig.matrix_world @ Vector(b.tail_local)

def hand_frame(side):
    """Measure a hand's own frame. The left hand is NOT the world-space mirror
    of the right -- mirroring by negating X put the left finger chains outside
    the mesh entirely -- so each hand gets its own measured basis and the digit
    table is applied in that frame with bar negated for the left."""
    gi = {g.name: g.index for g in mesh.vertex_groups}
    def w(v, n):
        i = gi.get(n)
        return next((g.weight for g in v.groups if g.group == i), 0.0) if i is not None else 0.0
    hv = [v for v in mesh.data.vertices if w(v, "hand." + side) >= 0.4]
    co = [mesh.matrix_world @ v.co for v in hv]
    hm = SB["hand." + side]
    fg = (hm.to_3x3() @ Vector((0, 1, 0))).normalized()
    o_ = hm.to_translation()
    t = [(c - o_).dot(fg) for c in co]
    lo_, hi_ = min(t), max(t)
    palm = [c for c, tt in zip(co, t) if lo_ + 0.20 * (hi_ - lo_) <= tt <= lo_ + 0.55 * (hi_ - lo_)]
    pc = sum(palm, Vector()) / len(palm)
    u = Vector((0, 0, 1)).cross(fg)
    if u.length < 1e-6: u = Vector((1, 0, 0)).cross(fg)
    u.normalize(); v2 = fg.cross(u).normalized()
    sxx = syy = sxy = 0.0
    for c in palm:
        d_ = c - pc; a_, b_ = d_.dot(u), d_.dot(v2)
        sxx += a_ * a_; syy += b_ * b_; sxy += a_ * b_
    th = 0.5 * math.atan2(2 * sxy, sxx - syy)
    e1 = (u * math.cos(th) + v2 * math.sin(th)).normalized()
    e2 = fg.cross(e1).normalized()
    v1 = sum(((c - pc).dot(e1)) ** 2 for c in palm)
    v2v = sum(((c - pc).dot(e2)) ** 2 for c in palm)
    br, nr = (e1, e2) if v1 > v2v else (e2, e1)
    if nr.dot(Vector((0, -1, 0))) < 0: nr = -nr
    cen = sum(co, Vector()) / len(co)
    # keep the right hand's basis exactly as the plates were measured
    if side == "R":
        Fm = MAP["frame"]
        return (Vector(MAP["palm_depth"]["centre_world"]),
                Vector(Fm["bar"]), Vector(Fm["nrm"]), Vector(Fm["fing"]))
    return cen, br, nr, fg

FRAME = {s: hand_frame(s) for s in ("R", "L")}
def hp(mm, side="R"):
    """hand-frame millimetres -> world, in that hand's own basis"""
    cen, br, nr, fg = FRAME[side]
    sgn = 1.0 if side == "R" else -1.0
    return (cen + br * (sgn * mm[0] / 1000.0) + nr * (mm[1] / 1000.0)
            + fg * (mm[2] / 1000.0))

bpy.ops.object.armature_human_metarig_add()
meta = bpy.context.object
meta.name = "rv_metarig"
meta.show_in_front = True

bpy.ops.object.mode_set(mode="EDIT")
EB = meta.data.edit_bones
# Face bones are exactly the descendants of spine.006. Do NOT match on
# substrings: "forearm" contains "ear", and a keyword filter deletes both arms.
def descendants(root):
    out, stack = [], [EB[root]]
    while stack:
        b = stack.pop()
        for c in b.children:
            out.append(c.name); stack.append(c)
    return out
removed = descendants("spine.006")
for n in removed:
    if n in EB: EB.remove(EB[n])
print("removed %d face bones (face is rigid on head by design)" % len(removed))

def resample(pts, n):
    seg = [(pts[i + 1] - pts[i]).length for i in range(len(pts) - 1)]
    tot = sum(seg); out = [pts[0]]; acc = 0.0; i = 0
    for k in range(1, n):
        target = tot * k / (n - 1)
        while i < len(seg) and acc + seg[i] < target: acc += seg[i]; i += 1
        if i >= len(seg): out.append(pts[-1]); continue
        f = (target - acc) / max(1e-9, seg[i])
        out.append(pts[i].lerp(pts[i + 1], f))
    return out

def place(name, h, t):
    b = EB[name]; b.head = h; b.tail = t

# ---- torso: hips -> spine -> chest -> neck resampled onto spine..spine.003 ---
torso = resample([head("hips"), head("spine"), head("chest"), head("neck")], 5)
for i in range(4):
    place("spine" if i == 0 else "spine.%03d" % i, torso[i], torso[i + 1])
neck = resample([head("neck"), head("head")], 3)
place("spine.004", neck[0], neck[1])
place("spine.005", neck[1], neck[2])
place("spine.006", head("head"), tail("head"))

for s in ("L", "R"):
    place("shoulder." + s, head("clavicle." + s), head("upperarm." + s))
    place("upper_arm." + s, head("upperarm." + s), head("forearm." + s))
    place("forearm." + s, head("forearm." + s), head("hand." + s))
    # hand tail is set later from the middle-finger knuckle. The source rig's
    # hand.L tail points 0.32 m away into empty space, so inheriting it produced
    # a 32 cm "hand" bone sticking out of the character.
    place("hand." + s, head("hand." + s), head("hand." + s) + Vector((0, 0, -0.02)))
    place("thigh." + s, head("thigh." + s), head("shin." + s))
    place("shin." + s, head("shin." + s), head("foot." + s))
    place("foot." + s, head("foot." + s), head("toe." + s))
    place("toe." + s, head("toe." + s), tail("toe." + s))
    # heel: across the back of the foot at ground level, from the mesh
    gi = {g.name: g.index for g in mesh.vertex_groups}
    fi = gi.get("foot." + s)
    fv = [mesh.matrix_world @ v.co for v in mesh.data.vertices
          if any(g.group == fi and g.weight > 0.5 for g in v.groups)]
    if fv:
        zmin = min(c.z for c in fv); rear = max(c.y for c in fv)
        xs = [c.x for c in fv]
        place("heel.02." + s, Vector((min(xs), rear - 0.005, zmin)),
              Vector((max(xs), rear - 0.005, zmin)))
    place("pelvis." + s, head("hips"), head("hips") + Vector(
        (0.06 if s == "L" else -0.06, -0.06, 0.06)))
    if "breast." + s in EB: EB.remove(EB["breast." + s])

# ---- fingers, from the plates -----------------------------------------------
MIDKNUCKLE = {}
ORDER = ["f_index", "f_middle", "f_ring", "f_pinky", "thumb"]
# The tips read a little past the actual fingertips, so the chains overshot the
# surface by 7-14 mm. Pull each tip back along its own chain.
# Fraction of the chord, not an absolute distance. A fixed 12 mm pullback on the
# pinky's ~19 mm chord left a 7.6 mm chain that owned zero vertices.
PULLBACK_FRAC = 0.14
PULLBACK_MAX = 0.010
for dname in ORDER:
    d = DIGITS[dname]
    cf, cn = ((THUMB_CURL_FING, THUMB_CURL_NRM) if dname == "thumb"
              else (CURL_FING, CURL_NRM))
    for s in ("R", "L"):
        cen, br, nr, fg = FRAME[s]
        b0, b3 = hp(d["base"], s), hp(d["tip"], s)
        chord = (b3 - b0).length
        b3 = b3 - (b3 - b0).normalized() * min(PULLBACK_MAX, chord * PULLBACK_FRAC)
        ctrl = (b0 + b3) * 0.5 + fg * cf + nr * cn
        pts = [b0 * (1 - t) ** 2 + ctrl * 2 * (1 - t) * t + b3 * t * t
               for t in (0.0, 1 / 3.0, 2 / 3.0, 1.0)]
        for i in range(3):
            place("%s.%02d.%s" % (dname, i + 1, s), pts[i], pts[i + 1])
        if s == "R":
            print("  %-9s chain length %.4f m (3 bones)" % (
                dname, sum((pts[i + 1] - pts[i]).length for i in range(3))))
        pi = {"f_index": "palm.01", "f_middle": "palm.02",
              "f_ring": "palm.03", "f_pinky": "palm.04"}.get(dname)
        if pi:
            place("%s.%s" % (pi, s), head("hand." + s), pts[0])
        if dname == "f_middle":
            MIDKNUCKLE[s] = pts[0].copy()

for s in ("R", "L"):
    place("hand." + s, head("hand." + s), MIDKNUCKLE[s])
    print("hand.%s length %.4f m" % (s, (MIDKNUCKLE[s] - head("hand." + s)).length))

bpy.ops.object.mode_set(mode="OBJECT")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("metarig bones after alignment: %d" % len(meta.data.bones))
print("ALIGN_DONE")
