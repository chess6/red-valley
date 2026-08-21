# Prepared ARDY `water_can` job — NOT RUN

Awaiting approval. No instance has been created and nothing has been spent.

## Division of responsibility

ARDY produces **body, arm, wrist and hand trajectory only**. Finger closure is
not its job and never was — that is supplied afterwards by the fixed
`grip_water_can.R` pose. This is why the earlier text-only attempts failed: they
were being asked to invent a grip they cannot represent.

## Prompt

```
A person stands upright and waters plants with a watering can held in the right
hand. Both feet stay planted. The torso leans forward slightly. The right arm
extends down and forward, holding the can away from the thigh and tilting it to
pour. The left arm hangs relaxed. The motion is calm and continuous.
```

## Constraint payload (end-effector reference, from the approved pose)

| constraint | value | source |
|---|---|---|
| right hand height | 0.79–0.85 m | reach-solved; below 0.79 m is unreachable without a deep fold |
| hand forward of hips | 0.26–0.36 m | approved pose reference |
| hand lateral of thigh | ≥ 0.15 m | clearance |
| trunk lean (hips→neck) | 10–15° | approved |
| hip drop | ≤ 0.03 m | approved: knees near straight |
| foot contacts | both planted, no lift | approved |
| left arm | relaxed, ≤ 0.22 m forward of hips | approved |

## Run parameters

| | |
|---|---|
| clip | `water_can` |
| duration | 8.0 s (160 frames @ 20 fps) |
| seed | 0 — single seed, no sweep |
| model | ARDY Core, official defaults |
| instances | exactly 1, destroyed immediately after |
| outputs | 1 |

## Cost estimate

Based on the previous 8-second pilots on the same instance class: roughly
5–8 minutes wall clock including model load, at the rate the guard has been
observing. **Estimated maximum: $0.10**, which is the cap I would set.

Preconditions before any instance is created, per `CLAUDE.md`:

- `tools/assetgen/vast.sh guard` returns 0 and the projected balance stays above
  the $6 stop line for the whole run
- started only through `tools/assetgen/vast.sh up`, never raw `vastai create`
- one instance, watchdog armed before creation
- destroyed within seconds if it cannot finish above the stop line

**Do not run without explicit approval.**
