# Rigify production-rig candidate

Separate from the accepted mesh and the frozen diagnostic rig; neither is
modified by anything here.

## Done

**Rigify enabled** (bundled with Blender 5.1.2). Its human metarig carries 159
bones including all 30 finger bones — `thumb.01/02/03`, `f_index`, `f_middle`,
`f_ring`, `f_pinky`, three each, both hands. That is exactly the structure the
custom rig could not produce.

**Orthographic hand plates** for explicit joint placement — `hand_palm.png` and
`hand_edge.png`, with `hand_ortho_mapping.json` giving an exact pixel-to-world
mapping so joints are read off rather than inferred:

    P = centre + right*((px/1400 - 0.5)*0.15) + up*((0.5 - py/1400)*0.15)

    centre  (-0.405972, -0.018986, 0.856489)
    palm    right = bar  (-0.171, -0.952,  0.252),  up = fing (-0.332, -0.186, -0.925)
    edge    right = nrm  ( 0.928, -0.242, -0.284),  up = fing (-0.332, -0.186, -0.925)

Two render problems were fixed to make these usable: the palm-side camera sat
inside the thigh (the palm faces the leg), so the hand is isolated first; and
the first edge plate was blown out to a single white mass, so exposure was cut.

The palm plate resolves all five digits. The edge plate shows the curl profile
and the thumb branching clear of the fingers.

## Remaining

1. Align the metarig — body from ortho body views, every finger and thumb read
   off the plates above. No automatic digit segmentation.
2. Generate the control rig.
3. Bind through the welded proxy; transfer weights to the UV-split mesh.
4. Preserve face rigidity (rigid on `head`, neck blending below the jaw) and the
   three proportion shape keys.
5. Add `prop_socket.R` on the verified palm contract (grip_anchor coincident,
   drift 1.5e-08 m).
6. Export deform bones plus root/socket only; exclude Rigify ctrl/mech bones.
7. Retarget the accepted walk; build one closed grip via finger and hand IK.
8. Validate shoulder, neck, fingers, face, foot contacts, Godot import, grip.
9. Render walk and grip beside the diagnostic rig.
