# water_can constraint reference (local, no cloud generation)

Hand-authored key poses used to *constrain* a later ARDY run rather than hoping
prompt wording produces them. Built by `tools/ardy/pose_reference.py` on
`derived/rv_player_proportioned.glb` with the diagnostic proxy can.
NOT_FOR_SHIPPING — the proxy can and the render ground/soil bed are scaffolding.

## Reach limit found while authoring

Shoulder sits at 1.5584 m and the arm (shoulder->wrist) is 0.7153 m, so the
lowest reachable wrist is 0.8431 m standing straight, and 0.7236 m at 15 deg
lean with 0.10 m of hip drop. **A 0.65 m hand height is not reachable** inside
the approved lean/hip-drop limits; it needs the deep fold those limits exclude.
The satisfiable window is ~0.72-0.80 m, so the poses sit at 0.79 m.

## Two angles are reported, and they differ

`trunk_lean_visible_deg` is the hips->neck axis, which is what reads on screen.
`trunk_lean_spine_chain_deg` is spine->neck. Rotating spine+chest by N degrees
yields only ~0.55N visible, because the hips segment of the trunk does not
rotate. The approved 10-15 deg band is applied to the *visible* angle.

## Measured (all three poses collision-free)

| | start | pour | return |
|---|---|---|---|
| visible trunk lean | 2.0 | **12.5** | 4.0 |
| hip drop (m) | 0.00 | **0.095** | 0.01 |
| hand height (m) | 0.881 | **0.791** | 0.871 |
| hand lateral of thigh (m) | 0.210 | 0.180 | 0.202 |
| hand forward of hips (m) | 0.094 | 0.323 | 0.135 |
| spout above soil (m) | 0.552 | **0.238** | 0.530 |
| spout downward component | -0.19 | -0.93 | -0.23 |
| body/can intersections | 0 | 0 | 0 |

Carried poses aim the can *upright*; the pour aims it nozzle-down and forward.
`pose_reference.py` raises if any pose intersects, so a colliding pose cannot
pass silently.

## Bug fixed while authoring

`tools/ardy/make_proxy_can.py` added a spurious `+ pi/2` yaw in `tube()`, which
built the spout pointing sideways across the body instead of forward-down, and
left `spout_tip` marking empty air 0.11 m past the geometry. Every earlier
spout measurement taken from that proxy was meaningless.
