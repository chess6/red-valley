# Right-hand grip attempt — regression gate PASSES, grip seating FAILS

## Delivered: hand regression checks (`tools/ardy/hand_regression.py`)

Wired as an abort gate: `grip_can_rigify.py` refuses to render if it fails.

- Palm direction is derived from **each hand's own thumb mass**, never shared
  between hands. Sharing one normal is exactly how the mirrored-sign error got
  in.
- Displacement is measured on the **deformed mesh**, not the bones, because a
  bone carrying no weight moves nothing a player can see.
- Asserts: curl moves index/middle/ring toward that hand's palm; hyperextension
  moves them away; left/right agree within 2 mm.

Current result — **PASS**:

| digit | R curl | L curl | R hyperext | L hyperext | delta |
|---|---|---|---|---|---|
| index | +11.4 | +11.4 | −20.2 | −20.6 | 0.0 mm |
| middle | +13.1 | +13.3 | −21.0 | −21.2 | 0.2 mm |
| ring | +4.1 | +4.0 | −7.7 | −7.1 | 0.1 mm |

## Grip anchor: exact

`grip_anchor` is coincident with the palm socket by construction. Measured drift
across the posed rig: **1.26e-07 m, 0.0000000 deg**.

## FAILED: the can does not seat in the hand

| digit | result |
|---|---|
| thumb | no collision-free pose at ANY closure, fully abducted to fully closed (89 intersections) |
| index | no collision-free pose at any closure (29 intersections) |
| middle | reaches full closure without ever touching the handle |
| ring | reaches full closure without ever touching the handle |
| pinky | left relaxed, as agreed |
| body/can | 35 intersections |

**This is not the pinky/ring limitation.** Thumb, index and middle are the
digits that work, and they are the ones failing here — the thumb and index are
inside the can, while the middle and ring cannot reach it. `grip/grip_palm.png`
shows the can passing straight through the hand.

### Probable cause: the proxy can is too big for this hand

The proxy's body is a cylinder of radius 0.085 m whose top sits only 0.0825 m
below the grip, while the whole hand is 0.095 m long. Seating the bar 0.0252 m
off the palm centre therefore puts the can body exactly where the thumb and
index have to be. A real watering can has a thin handle arch with clear space
for a hand inside it; this proxy does not.

That is a property of the diagnostic proxy, not of the Rigify bind — the same
collision defeated the abandoned custom rig at the same point.

**Stopped here. No further automatic binding method attempted.**
