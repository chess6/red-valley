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
| visible trunk lean | 2 | 12.51 | 4 |
| hip drop (m) | 0 | 0.06 | 0.01 |
| hand height (m) | 0.88 | 0.79 | 0.87 |
| hand lateral of thigh (m) | 0.2188 | 0.1508 | 0.2088 |
| hand forward of hips (m) | 0.1 | 0.2607 | 0.14 |
| spout above soil (m) | 0.5543 | 0.2722 | 0.5164 |
| spout downward component | -0.184 | -0.923 | -0.27 |
| knee gap (m) | 0.2362 | 0.2897 | 0.2904 |
| body/can intersections | 0 | 0 | 0 |

Carried poses aim the can *upright*; the pour aims it nozzle-down and forward.
`pose_reference.py` raises if any pose intersects, so a colliding pose cannot
pass silently.

Soles measure z = 0.0000 in all three poses.

## Bugs fixed while authoring

The leg solver used CCD, which constrains the end effector but never the joint
swivel: the thighs rotated inward and the knees crossed, while foot height
stayed equal and every automated check passed. A human caught it in the render.
Legs and elbow now use an analytic two-bone solve with an explicit pole, so a
crossed knee is not representable, and knee separation is reported.


`tools/ardy/make_proxy_can.py` added a spurious `+ pi/2` yaw in `tube()`, which
built the spout pointing sideways across the body instead of forward-down, and
left `spout_tip` marking empty air 0.11 m past the geometry. Every earlier
spout measurement taken from that proxy was meaningless.
