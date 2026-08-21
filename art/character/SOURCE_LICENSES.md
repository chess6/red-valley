# Source Assets — Licensing Record

> **The shipping player character is the Hyper3D Rodin export, recorded below.**
> The MakeHuman/MPFB2 material further down is the SUPERSEDED earlier lineage
> (`Player_HiFi_v01..v05`). Until 2026-08-21 this file documented only that superseded
> character, so the asset actually in use had no licence record at all.

## Player character — Hyper3D Rodin (SHIPPING)

| item | value |
|---|---|
| Asset | `rodin_export_c40a04c4.zip` → `base_basic_pbr.glb`, `base_basic_shaded.glb` |
| Derived baseline | `art/animation/ardy_pilot/derived/rv_player_proportioned.glb` |
| Generated | 2026-08-19 |
| Job / asset id | `c40a04c4` (from the export filename; the account UI exposes no separate id) |
| Service | Hyper3D **Rodin** |
| Plan | **Creator (paid)** — a subscription is required even to download the model |
| Terms | https://hyper3d.ai/legal/terms — snapshot `licence_evidence/hyper3d_terms_2026-08-21.md` |
| **commercial_use** | **allowed (plan-dependent)** |
| **copyright_ownership** | **NOT transferred** — see below |
| Export SHA-256 | `3b011e963363dd59c8fa595f8307ef34124a29ca4a76aac82fa69015b1c0ffcf` |
| Derived GLB SHA-256 | `05340d9c95781e9f69d0084e99e6f29ffbf8b3daba5491ba5e24620b14152aba` |
| Cleared by | Thomas (project owner), 2026-08-21, on the clauses quoted in the snapshot |

### Why "allowed", not "owned"

§5(a) says Hyper3D "will not limit your use of such Output". That is a **covenant
not to restrict**, not an assignment of copyright. §5 separately disclaims any
warranty that Output is copyrightable or that IP rights in it can be registered or
credited to anyone. So the defensible record is permission to use commercially on
a qualifying plan — recording `copyright_ownership: transferred` would assert
something the terms do not say.

### Two live risks, recorded not resolved

1. **The terms are unversioned.** The page shows only "Current version" with no
   date, so they can change silently. The dated snapshot is the mitigation;
   re-verify before shipping and before any future clearance.
2. **Training-data provenance is unauditable.** §5's disclaimer places the
   copyrightability question on the user. This is a judgement call about
   acceptable risk, not a licence defect, and it is the project owner's to make.

---


## Superseded lineage — MakeHuman / MPFB2

Generated 2026-08-17. **Superseded by the Rodin character above**; retained because it is hand-made rather than generated, and is the fallback body if the Rodin risks above are ever judged unacceptable.

Originals are preserved unmodified in `source_assets/makehuman/`.

## Tooling

| Component | Version | License | Source |
|---|---|---|---|
| MPFB2 (MakeHuman Plugin for Blender) | 2.0.17 (build 20260817) | **GPL-3.0-or-later** (addon code) | http://static.makehumancommunity.org/mpfb.html |
| Blender | 5.1.2 | GPL | blender.org |

> MPFB's *generated output* (meshes/characters) is not GPL-encumbered; MakeHuman
> publishes its base mesh and system assets under CC0. Verify before shipping.

## Downloaded packs

| Pack | License (per filename) | SHA-256 (16) | Size | Assets in manifest |
|---|---|---|---|---|
| `eyebrows01_cc0.zip` | **CC0** | `5425891dce613bef` | 11 MB | 14 |
| `eyelashes01_cc0.zip` | **CC0** | `b7b5eb97cfb930d9` | 3 MB | 5 |
| `makehuman_system_assets_cc0.zip` | **CC0** | `b542127a8e25547c` | 281 MB | 94 |
| `shoes01_cc0.zip` | **CC0** | `ded3f70428505eab` | 83 MB | 23 |
| `shoes02_ccby.zip` | **CC-BY** | `1b544d87dd8b3d3a` | 106 MB | 24 |
| `shoes03_ccby.zip` | **CC-BY** | `7818b43a520a90bb` | 50 MB | 12 |
| `skins01_cc0.zip` | **CC0** | `7495ab99287053bd` | 104 MB | 23 |
| `system_eye_materials01_cc0.zip` | **CC0** | `acad4636c08ff96a` | 14 MB | 13 |

## Assets actually imported into the character

| Asset | Role | License | Author | Source |
|---|---|---|---|---|
| `male_casualsuit01` | Shirt (collar+sleeves) | **CC0** | makehuman_system | http://www.makehumancommunity.org |
| `female_casualsuit01` | Jeans | **CC0** | makehuman_system | http://www.makehumancommunity.org |
| `mindfront_shoes_biker_boots_female` | **Boots** | **CC-BY** | Mindfront | http://www.makehumancommunity.org/node/623 |

## Attribution required in game credits

`mindfront_shoes_biker_boots_female` is **CC-BY**, so shipping requires visible credit:

> Boots based on "Shoes Biker Boots Female" by **Mindfront**, from the MakeHuman
> Community asset library, licensed under **Creative Commons Attribution (CC-BY)**
> — https://creativecommons.org/licenses/by/4.0/ — **modified** (reshaped to
> mid-ankle height, retextured to brown leather) for Red Valley.

CC0 assets require no attribution, but are credited here for provenance.

## Modifications made

| Asset | Modification |
|---|---|
| `male_casualsuit01` | Trousers half removed by planar bisect; sleeves bisected to mid-forearm; recoloured to cream cotton |
| `female_casualsuit01` | Tee component deleted (whole connected component); recoloured to dark denim |
| `mindfront_shoes_biker_boots_female` | *Pending:* shorten shaft to mid-ankle, recolour to brown leather |
| `young_caucasian_female` | Base colour retained; procedural pore normal / roughness / SSS added |

## Rejected candidates

| Asset | License | Reason |
|---|---|---|
| `toigo_ankle_boots_female` | CC0 | Correct height but smooth bootie, no outsole/lacing structure — quality not equivalent |
| `maciekg_leather_boots` | CC-BY | Only 696 verts and references a **missing texture** (`boots_ao.png`) — incomplete asset |

No NC, ND, unknown or incomplete-licence assets were imported.
