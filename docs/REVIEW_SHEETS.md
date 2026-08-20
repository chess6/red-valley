# Milestone review sheets — provenance record

The review images themselves are **not tracked in Git**. They are preserved
locally and, for the masters, in the private asset store. This file keeps the
record: what each sheet showed, and its SHA-256 at the time of the decision.

Regenerate any of them with the noted script; a matching checksum proves the
regenerated image is byte-identical to the one that was reviewed.

| sheet | milestone / what it showed | regenerate with | sha256 |
|---|---|---|---|
| `final_front.png` | Character acceptance — approved Rodin player, front | `art/character/scripts/` | `4527e2834118a4cd71400357735bfa2589f8879a3b0da020dbeef8e5234185fc` |
| `02_pour_side.png` | water_can constraint reference, pour pose, true side | `tools/ardy/pose_reference.py + render_poses.py` | `152cf6e7b99b4da19477adfa6f66e4ebb7210dfbecd765718fa765689f6467fb` |
| `overlay_front.png` | Rigify iteration 1 — metarig/deform-bone overlay, front | `tools/ardy/overlay_rigify.py` | `61e95ceec99242c186319138c0dae2ed7df7e586310a221007b5563a6f5ea55f` |
| `fist_R.png` | Rigify iteration 2 — right fist after per-hand curl fix | `tools/ardy/matched_hands.py` | `d49c45c7e37e33a162cf649b576d169425fcb2fb3e45b2c879efaf987ebf0f33` |
| `fusion_palm.png` | Fused-digit evidence — 4 components for 5 digits | `tools/ardy/hand_region.py` | `1fa167708dc5213a9d03883fac5e0adb684f4f5cad2eab1ad1940759616094ab` |
| `grip_palm.png` | Grip attempt — proxy can interpenetrating the hand | `tools/ardy/grip_can_rigify.py` | `1702e727dc80aa23d23d1e2e618a1e24abe6cacf214838430da32279b1639311` |
| `upload_hand_outer.png` | Mixamo evaluation — uploaded hand geometry, five separated digits | `tools/ardy/bake_for_autorig.py` | `736bbb27fa18658e02599ca0b5948f3c6b9045a9593a81345981ab789ed1184f` |

## Superseded character sources (untracked, preserved privately)

The six `Player_HiFi_v0*.blend` files are the authored MakeHuman/scripted
character lineage, superseded by the Rodin character. Preserved in
`~/RedValleyAssets/masters/`; see that store's MANIFEST.sha256.

- `Player_HiFi_v01.blend` — `8b38f1945d21d2d08e4e62d16e0e05e39d7c4790724710c92a67f98a51ef620b`
- `Player_HiFi_v01_diagnostic.blend` — `0cf2e90d73772a1c321d3d811ed126eef1ea6e2570f438b39b00ef4ef9660c44`
- `Player_HiFi_v02_scripted_outfit.blend` — `6f1f36f64e1cf5a88572581ab82d997e4a43e812444cc869b5c8e10b7c2d0ce0`
- `Player_HiFi_v03_cloth_outfit.blend` — `05ad3357b2732d87173854bab7f238be5e51d6d236467f7d49de5221979266c8`
- `Player_HiFi_v04_vest.blend` — `98ff11c77a353757e516fb93ef30697e9d44f0e182e123f6e8594b69afeec071`
- `Player_HiFi_v05_asset_vest.blend` — `f3a435803066098e45482f14c7d40b85461f0bea31643231f56ab5f95e9efba2`
