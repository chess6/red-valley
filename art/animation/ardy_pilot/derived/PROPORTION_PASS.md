# Proportion pass — derived copy

**The Rodin master is untouched.** `base_basic_pbr.glb` remains read-only and
its checksum still verifies. Everything here is a derived copy.

## Method: reversible shape keys

| Shape key | Change | Vertices moved |
|---|---|---|
| `fix_neck_width` | X scaled to 92% over z 0.835-0.895 (raised-cosine falloff) | 11,376 |
| `fix_waist_width` | X scaled to 95.5% over z 0.575-0.660, symmetric about x=0 | 16,328 |
| `fix_pelvis_thrust` | +1.5 cm backward over z 0.455-0.570, tapered | 16,345 |

All three ship at value 1.0. **Setting them to 0 restores the original mesh to
within 2.2 microns** (float precision) — verified, not asserted.

## What is preserved

| | master (rigged) | derived |
|---|---|---|
| Vertices | 70,040 | 70,042 |
| Triangles | 49,994 | 49,994 |
| UV layers | `UVMap` | `UVMap` |
| Materials | `model` | `model` |

Triangles, UVs, material and vertex order are unchanged; nothing is remeshed.
The +2 vertices are a glTF morph-target round-trip artifact, not geometry work.
Vest, belt and all textures are untouched — only vertex positions move, so
texture mapping is unaffected.

## Neck articulation (a weight fix, not a shape change)

The neck region was dominantly weighted to the `head` bone (2,636 verts vs 841
on `neck`), so the neck bone barely moved the mesh. Weight is now blended back
toward `neck` across the neck column, leaving the skull on `head`:

| | mesh response to an 8 deg neck input |
|---|---|
| before | 1.5 deg |
| after | **4.4 deg** |

Roughly 3x the authority. 4,602 vertices rebalanced.

## What this pass is NOT

It does not conceal rigging defects. Those remain recorded and unchanged:

- ARDY's own head-forward motion still adds ~9 deg over the mesh baseline.
- `forearm.R` still grazes `hips` at frames 33-35 (z 1.05-1.09 m), 188/192
  frames clean.
- No spine or neck correction is applied in the shipped walk; both are off.
