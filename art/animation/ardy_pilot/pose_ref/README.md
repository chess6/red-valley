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
| hip drop (m) | 0 | 0.025 | 0.005 |
| hand height (m) | 0.88 | 0.8417 | 0.88 |
| hand lateral of thigh (m) | 0.2188 | 0.1578 | 0.2188 |
| spout above soil (m) | 0.5313 | 0.29 | 0.5134 |
| can tilt off vertical (deg) | 7.2 | 47 | 5.9 |
| head pitch below horiz (deg) | 10.4 | 41.2 | 10.4 |
| left hand fwd of hips (m) | 0.1186 | 0.2138 | 0.1371 |
| knee gap (m) | 0.2362 | 0.2902 | 0.2905 |
| body/can intersections | 0 | 0 | 0 |

Soles measure z = 0.0000 in all three poses.

Knee angle 172.8 deg carrying, 151.8 deg pouring (180 = straight). Nozzle sits
over the bed at y = -0.309 (bed spans -1.25..-0.25).

## Why the can orientation is constructed, not searched

Rolling about the arm axis plus a world-X pitch spans only two of the three
rotational degrees of freedom, so "body tilted ~47 deg forward AND spout steeply
down-forward" is unreachable by that search -- it returned a tilt in range with
the nozzle far too high. The orientation is now built directly from the can's
fixed internal geometry: grip->tip is 0.323 m at 68.2 deg off the body axis, so
a tip 0.15-0.30 m above soil *requires* a body tilt of at least ~46 deg. Hand
height then follows from the orientation rather than being set independently.
A yaw sweep finds the first orientation that clears the thigh.

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

## Grip contract (validated)

`grip_anchor` marks the exact centre and axis of the handle bar: Y along the
bar, Z toward the can body. The can is attached as `sock @ anchor.inverted()`,
so grip_anchor and `prop_socket.R` are coincident by construction rather than by
a fudge offset. Measured drift across start/pour/return: **1.5e-08 m, 0.0 deg**.

`prop_socket.R` sat at 58% along the hand -- under the fingertips. It deforms
nothing (0 weighted vertices), so it was relocated into the palm.

The handle bar was widened 0.100 -> 0.140 m. The hand is 0.095 m across the bar
axis and the old clear span between the struts was 0.082 m, so the hand could
not fit inside its own handle.

### The finger wrap is NOT solved

`grip_can` exists (294 vertices, 28 deg curl, zero intersections) but does not
read as a grip. The bar has to sit 0.0388 m off the palm centroid to clear the
thumb, which protrudes ~0.025 m on the palm side; at that distance the hand
reads as open beside the handle. Sitting the bar on the palm surface (0.0258 m)
intersects in every pose at every curl angle from 0-100 deg.

The zero-intersection metric is satisfied *trivially* here -- by holding the
handle away from the hand. It is not evidence of a grip. Closing this properly
needs finger bones in the rig, not a larger shape key: a single hinge curl
cannot oppose a thumb, and nothing else can hold a handle.

Note also that a procedural finger curl is the kind of organic deformation
`docs/ASSET_POLICY.md` rules out. It is reversible and confined to the derived
copy, but it is not the right mechanism.

## Face deformation: measured, was real, now fixed

Not perspective. Before: 55.2% of the 3039 face vertices carried non-`head`
weight (6.3% of face weight sat on `neck`), and face edges stretched by up to
**21.2%** (start) and **28.6%** (return).

Face and skull are now rigid on `head`, with neck blending confined to a 0.02 m
band below the jaw plane (z = 1.7104). After: **0** non-rigid face vertices, max
edge-length change **0.0074%**. `face_00_rest.png` and `face_start.png` are
pixel-identical, from one fixed camera.
