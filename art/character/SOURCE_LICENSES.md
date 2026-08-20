# Source Assets — Licensing Record

Generated 2026-08-17 for the Red Valley protagonist.

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
