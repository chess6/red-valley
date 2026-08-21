# `water_can` interaction contract (generator-neutral)

One contract, applied identically to Kimodo and ARDY, so the comparison is about
the generators and not about two different requests. Encoded programmatically by
`tools/rvmotion/build_water_contract.py` against each generator's own constraint
classes; nothing here is hand-written JSON.

## Timing

| item | value | why |
|---|---|---|
| duration | **2.4 s** (48 frames @ 20 fps) | a natural reach-pour-return. **No compression to the 1.2 s one-shot during the architectural comparison** — retiming is a delivery step and would confound the generator A/B |
| pour window | frames 22–36 (1.10–1.80 s) | the spout must be over the bed for this span |

## Foot contract — sparse, and it must produce a step

| phase | frames | constraint |
|---|---|---|
| settle | 0–8 | **both feet planted** at their start positions |
| release | 9–19 | **lead (left) foot unconstrained** — the transition is deliberately not prescribed |
| land | 20–47 | lead foot planted **0.28 m forward** of its start, in a modest stagger |
| support | 0–47 | **rear (right) foot planted throughout** |

This is the specific defect in the existing ARDY baseline: that run pinned *both*
feet for the whole clip, so no step was possible. That clip is therefore **not a
valid generator comparison** and is excluded from the A/B.

## Hand contract — derived from the can's own markers

The can is a rigid body with a measured grip anchor and spout tip
(`art/animation/ardy_pilot/proxy/watering_can_proxy.json`), so the hand
constraint is *derived*, not guessed:

```
spout_tip_local  = (0.000, -0.300, -0.150)   # 0.335 m from the grip
grip_anchor      = Y along the handle bar, Z toward the can body
```

Given a target spout position `S` over the bed and a pour tilt `θ` about the bar
axis, the required wrist transform is
`W = T(S) · R(bar, θ)⁻¹ · A⁻¹`, where `A` is the grip-anchor basis. The hand
**position and rotation** constraints are read off `W`.

| item | value |
|---|---|
| spout target, pour window | bed + **0.22 m**, the documented mid-band. Asked for directly; if a body cannot reach it the escalation is reported, never silently substituted |
| spout stand-off from plot edge | 0.10 m inside the bed |
| hand rotation | from the grip anchor, so the handle sits in the palm and the spout points down-forward |
| carry frames (0–8, 44–47) | can hangs at the side, bar axis horizontal |

## Posture contract

| item | value | why |
|---|---|---|
| pelvis travel | ≤ 0.15 m forward | the reach should come from the step and the arm, not a deep hip hinge |
| spine signed curvature | **neutral**: per-segment sagittal pitch within ±12° of upright at the pour | the existing baseline reaches by hinging the trunk to 23°, which reads as a bow rather than a reach |
| hand height | never below 0.35 m | prevents a crouch substituting for a step |

Deliberately **unconstrained**: the transition itself, arm swing, weight shift,
knee flexion, and every frame outside the listed windows.
