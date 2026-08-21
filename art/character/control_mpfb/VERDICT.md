# MPFB CC0 control character — verdict

**Question:** the Rodin mesh's hands resisted four separate segmentation attempts.
Is that the **topology**, or is it **our binding pipeline**?

**Answer: the topology.** The same pipeline, measured identically, produces
complete digit weighting on a clean mesh.

## Like-for-like

Both measured the same way: vertex groups matching a digit name, restricted to
groups that correspond to an actual **deform** bone on the armature that deforms
that mesh, counting vertices whose dominant weight in the group exceeds 0.5.

| | Rodin (production) | MPFB control (CC0) |
|---|---|---|
| mesh vertices | 70 042 | 19 158 |
| deform bones | 71 | 163 |
| digit deform groups | 30 | 30 |
| **groups with ZERO dominant vertices** | **13** | **0** |
| median vertices per digit group | 37 | 96 |

The 13 empty groups on the production mesh are the **entire pinky on both hands**
(`.01/.02/.03`), most of the **ring** finger, and the **thumb** base and middle
joints. Those digits have no geometry that can be assigned to them — which is why
weight-based selection, geometry-only selection, a custom finger rig and Mixamo's
autorigger all failed in different ways. Nothing downstream can recover
articulation that the mesh does not contain.

The control character has a third of the vertex count and weights every digit.

## What this settles

- The binding pipeline is **not** the defect, and further segmentation attempts on
  the Rodin hands would be wasted. `docs/ASSET_BLOCKERS.md` already forbids a
  fifth attempt; this is the evidence for that call.
- The finger limitations recorded against `water_can` and `walk_fwd` are an
  **asset** limitation, correctly attributed.
- Retopologising the production hands is the fix, and it is now justified by
  measurement rather than by repeated failure.

## Status of this asset

**Test asset. Not for shipping, not a replacement character.** It exists to
answer the question above and to give the pipeline a clean-topology control when
something needs isolating. MakeHuman's base mesh and system assets are CC0, so it
carries no licence risk; MPFB2 itself is GPL-3.0-or-later but that governs the
addon code, not generated output.

Rebuild with:

    blender --background --python tools/rvmotion/build_mpfb_control.py -- art/character/control_mpfb
