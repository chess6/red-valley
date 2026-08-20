# Local finger rig — built, not yet converged

`tools/ardy/add_fingers.py` extends the accepted rig into
`derived/rv_player_fingers.glb`. The master and `rv_player_proportioned.glb`
are unchanged.

## What exists

**53 bones** (23 original + 30 new). Symmetric: three deform bones per digit,
five digits per hand, parented under `hand.R` / `hand.L`. No existing body bone
was moved, and only weight already sitting on `hand.R` / `hand.L` was
redistributed, so no non-hand weight changed.

All 30 digit bones carry weight in the exported file: 670 vertices are dominated
by a digit bone and 1976 carry some digit weight.

## What has not converged

Weight capture reaches only the distal part of each digit. The rest-hand colour
pass shows the fingertips owned by their chains and the finger bodies still on
`hand.R`/`hand.L` (729 / 646 vertices). The likely cause is the 0.013 m capture
radius, which suits the slim distal phalanges but not the thicker proximal ones.

The grip pose was not attempted — the two-iteration limit was spent on the rig.

## Approaches that failed, so they are not retried

- **Mesh connectivity segmentation.** The GLB's UV splits fragment the hand;
  the largest component above the knuckle was 87 of ~500 vertices.
- **Spatial clustering (DBSCAN).** Finger mesh spacing exceeds the inter-digit
  gap, so 4 mm eps returns 107 singletons and larger eps merges digits.
- **Tip-band gap splitting.** Merges pairs — produced 94- and 92-vertex
  "digits", and a thumb measuring 0.082 m on one hand and 0.0144 m on the other.
- **Straight knuckle-to-tip chains.** The rest fingers are curled, so a straight
  chain passes through air and captures only the tips.

What currently works is tracking each digit as a tube from its tip, re-centring
on the local cross-section at each step, which follows the curl.
