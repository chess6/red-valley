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

## Result of run 1: wrong skeleton LOD — benchmark inconclusive

Downloaded `T-Pose.fbx` (sha256 `68c06741…6ec2c81f`) and `Defeated.fbx`
(sha256 `edd0ea0d…235946b0`). Both carry the same skeleton.

### Mesh integrity: PASS

| | baseline | returned |
|---|---|---|
| vertices | 70,042 | 70,042 |
| triangles | 49,994 | 49,994 |
| height | 1.9005 m | 1.9028 m |
| unweighted verts | — | 0 |

Counts are exact; the 2.3 mm (0.12%) height change is the T-pose re-posing plus
the FBX round trip. Mixamo did not damage the mesh.

### Finger rigging: FAIL as delivered

33 bones, not 65. This is Mixamo's **No Fingers (25)** skeleton: 25 body bones
plus one index chain per hand acting as a hand terminator.

    LeftHandIndex1..4, RightHandIndex1..4     -- and nothing else

No thumb, middle, ring or pinky on either hand. A thumb is precisely what the
custom rig lacked, so this run cannot answer the question the benchmark exists
to answer.

This is a skeleton-LOD selection, not a Mixamo capability limit — Standard
Skeleton (65) does provide four joints per digit on both hands. One re-rig with
that LOD selected would settle it.

### Weight asymmetry worth correcting on any re-run

Vertices dominated by each bone:

| bone | verts | | bone | verts |
|---|---|---|---|---|
| LeftHandIndex1 | 896 | | RightHandIndex1 | 226 |
| LeftHandIndex2 | 544 | | RightHandIndex2 | 520 |
| LeftHandIndex3 | 400 | | RightHandIndex3 | 226 |
| LeftHand (palm) | 477 | | RightHand (palm) | 1223 |

The two hands were fitted very differently — the right palm claims 2.6x the
vertices of the left. That usually means the wrist markers were not placed
symmetrically. The right hand is the one that has to hold the can.

### Not proceeding to retarget or grip

Without a thumb a closed grip cannot be built, which is the whole object of the
exercise. Retargeting the walk onto a skeleton we expect to replace would be
discarded work. Stopped here, per the brief.

`Defeated.fbx` (203 frames @ 30 fps) is on the same 33-bone skeleton so it is
not usable yet, but it is a good shoulder/spine deformation stress test once a
usable skeleton exists — a slump exercises exactly the joints under review.

## Why only index chains — geometry ruled out

Checked the two documented causes of Mixamo dropping finger bones, on the exact
mesh that was uploaded:

| suspected cause | measured | verdict |
|---|---|---|
| fused / mitten digits | 7 gaps >2.5 mm across the fingertip band, max 8.0 mm | ruled out |
| hands crowding the body | min hand->body distance 0.1468 m; 0 verts within 10 mm | ruled out |
| mesh damaged on return | 70,042 verts / 49,994 tris returned exactly | ruled out |

`handcheck/upload_hand_*.png` show five properly separated digits, thumb
included. The source geometry is not the problem.

The result is also *symmetric and exact*: both hands received precisely an
Index1..4 chain and nothing else. A geometry-segmentation failure would be
expected to fail unevenly between hands — and this rig is already known to have
fitted the two hands unevenly (right palm claims 2.6x the left's vertices), so
the fitter clearly did treat them differently. Finger bones nevertheless came
out identical on both sides. That pattern points at a skeleton LOD applied after
fitting, not at a failure to find the fingers.

Since 25 + 8 = 33 exactly, what came back is the No-Fingers skeleton plus a
single index chain per hand as a terminator.

### Recommendation

One more auto-rig, with the Skeleton LOD dropdown confirmed to read "Standard
Skeleton (65)" at the moment the rigger finishes, and the finger count checked
in Mixamo's own preview before downloading. If it returns 33 bones again with
the LOD visibly set to 65, Mixamo is not going to rig this mesh's fingers and
the benchmark closes as negative.

Do not straighten the fingers to help the fitter: posing fingers requires finger
bones, which is the thing being sought.

## VERDICT: EVALUATED-NEGATIVE (2026-08-19)

Two independent auto-rigs, both returning 33 bones with no thumb:

| run | file | sha256 | bones | thumb |
|---|---|---|---|---|
| 1 | T-Pose.fbx | `68c06741…6ec2c81f` | 33 | none |
| 2 | T-Pose_run2.fbx | `f7d18f5a…8a3dbee9` | 33 | none |

Run 2 returned *identical* finger weighting to run 1 — 1840 index-dominated
vertices on the left, 972 on the right, in both runs — while the palm asymmetry
persisted (2.56x, then 2.64x). Mixamo produces this exact skeleton for this mesh
regardless of marker placement.

`GrabRifle_run2.fbx`, a gripping animation, confirms it from the other side:
`RightHandIndex1` rotates 23.5 deg over the clip while `Index2` and `Index3`
move 3.9 and 2.1 deg. There is nothing else to curl.

Geometry was ruled out first: digits separated (gaps to 8.0 mm), hands 0.1468 m
clear of the body, mesh returned with exact vertex and triangle counts.

**No further Mixamo uploads or re-rigs.** Returned files preserved under
`rigged/`.
