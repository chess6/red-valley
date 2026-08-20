# FROZEN: custom armature = diagnostic rig only

As of 2026-08-19 the custom `rv_rig` is **frozen as the diagnostic rig**. It is
not a production candidate and must not be extended further.

| asset | role |
|---|---|
| `derived/rv_player_proportioned.glb` | accepted mesh + 23-bone rig — DO NOT MODIFY |
| `derived/rv_player_fingers.glb` | 53-bone finger experiment — ABANDONED, diagnostic only |
| `art/animation/rigify/` | Rigify production-rig candidate — in progress |

The 23-bone rig remains valid for everything it already does: body motion,
retargeting, the pose reference, and the prop socket contract. Its one defect is
that it cannot close a hand, which is what the Rigify candidate exists to fix.

Do not resume `tools/ardy/add_fingers.py`. See `FINGER_RIG_STATUS.md` for the
five segmentation approaches that failed and why.
