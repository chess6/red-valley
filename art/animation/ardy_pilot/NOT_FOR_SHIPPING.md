# NOT FOR SHIPPING

Everything in this directory is **diagnostic apparatus for the ARDY motion
pilot**. None of it is a game asset and none of it may be promoted into
`assets/`.

`.gdignore` keeps Godot from importing any of it, so it cannot be referenced
from a scene by accident.

## What lives here

| Item | Purpose |
|---|---|
| `proxy/watering_can_proxy.glb` | **Measurement rig, not a prop.** Script-generated primitive geometry whose only job is to carry an exact `grip_origin` and `spout_tip` so `water_can` alignment can be measured rather than eyeballed |
| `proxy/watering_can_proxy.json` | The marker offsets, for automated acceptance tests |

## Replacement contract

After the pilot, the proxy is replaced by a **provenance-cleared, high-quality
watering can** which must preserve the same attachment contract:

- mesh origin at the grip point
- a `grip_origin` marker at the origin
- a `spout_tip` marker at the spout opening centre
- prop local −Z running along the forearm when parented to `prop_socket.R`

Preserving that contract is what lets the real can drop in without re-authoring
the clip or the tests.

**Do not let this proxy quietly become the shipped watering can.**

## Verified against the proxy

- Grip-to-socket distance: **0.0000 m** — the attachment contract holds exactly.
- The can hangs body-down with the spout forward when attached via
  `sock @ Matrix.Rotation(radians(90), 4, "X")` (see `docs/SKELETON_SPEC.md`).
- Proxy is 340 triangles, spout tip 0.323 m from the grip.
