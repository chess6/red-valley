# Mixamo autorig benchmark (evaluation only)

Benchmarking a third-party autorigger before investing further in homemade
finger rigging. The current rig and the accepted derived asset are NOT touched
by anything in this directory.

## Upload copy

`upload/rv_player_neutral.fbx` — one baked, neutral-pose copy.

| | |
|---|---|
| source | `art/animation/ardy_pilot/derived/rv_player_proportioned.glb` |
| source sha256 | `05340d9c95781e9f69d0084e99e6f29ffbf8b3daba5491ba5e24620b14152aba` |
| output sha256 | `6df24eeca4fb5eba0664a77ccec406c310cda4e00ceb9fd227f4ff723e564428` |
| size | 10,370,124 bytes |
| geometry | 70,042 verts / 49,994 tris, single mesh |
| height | 1.9005 m |
| pose | neutral rest (no bone carried a non-rest pose) |
| stripped | `Icosphere` (stray helper), `rv_rig` (armature) |
| baked | `fix_neck_width`, `fix_waist_width`, `fix_pelvis_thrust`, all at 1.000 |
| vertex groups | cleared — Mixamo re-rigs from scratch |
| built by | `tools/ardy/bake_for_autorig.py`, Blender 5.1.2 |

A stray `Icosphere` (42 verts) was present in the accepted GLB and has been
excluded, per "no props, cameras or helpers".

Known gap: the FBX re-imports with the diffuse and normal maps embedded but not
the packed metallic/roughness map. It does not affect autorigging, and shipping
materials come from the master rather than from Mixamo's output.

## Acceptance criteria for the returned rig

1. Finger and thumb bones present, three joints per digit, both hands.
2. Finger weights actually influence finger vertices (not collapsed to the palm).
3. Mesh returned undamaged: vertex count, height and silhouette preserved.
4. Shoulder and neck deformation no worse than the current custom rig.

If 1 or 3 fails, stop and report. Do not start another custom repair loop.
