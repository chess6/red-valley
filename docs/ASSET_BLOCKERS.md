# Asset blockers — deformation, not animation

These are properties of the **mesh and its topology**. No retargeter can fix
them, and no more effort should be spent inferring structure that is not there.

## 1. Fused hand topology (BLOCKER, was being worked around)

The Rodin master's hand is a fused mass with no clean per-digit loops. Every
automated attempt to recover five separable digits failed in a different way,
across three binding methods and one external autorigger:

| attempt | outcome |
|---|---|
| custom finger chains, 3 iterations | abandoned permanently by instruction |
| Mixamo autorig | EVALUATED-NEGATIVE (33 bones, no usable digits) |
| Rigify + weight-based hand selection | pinky unweighted, ring weak |
| Rigify + geometry-only selection | inconclusive; "fingers melted together" |

**Recorded as an asset blocker. Do not attempt a fifth segmentation method.**

### Settled by measurement (2026-08-21)

The CC0 MPFB control character answers it: the same pipeline, measured
identically, gives **0 empty digit groups out of 30** on clean topology against
**13 of 30 empty** on the Rodin mesh — the whole pinky on both hands, most of the
ring, and the thumb base. The binding pipeline is not the defect; the geometry is.
Full comparison: `art/character/control_mpfb/VERDICT.md`.

### Bounded options

| option | what it costs | what it gives |
|---|---|---|
| **A. Retopologise the hands** on the existing master | a modelling pass by a human; the rest of the character is untouched and already approved | keeps the approved silhouette and identity; clean digit loops |
| **B. CC0 MPFB/MakeHuman body + hand baseline** | MPFB is already installed in this Blender (`mpfb.init` in every log); a test rig can be built and bound in one session at zero licence risk | a known-clean topology to prove the pipeline end-to-end, and a fallback body if the Rodin licence question goes the wrong way |

**Recommendation: B first as a pipeline control, then A for production.** B is
cheap and answers a question A cannot: whether the remaining hand defects are
topology or binding. It is a *test asset*, not a replacement character.

**Not done in this task:** the production mesh was not altered.

## 2. Jaw/neck blend band — NOT CONFIRMED (2026-08-21)

The old aggregate "face deviation" gate mixed two populations and was
meaningless. Measured separately:

| region | definition | worst edge strain | verdict |
|---|---|---|---|
| rigid face core | 7 922 verts, `DEF-spine.006` weight > 0.999, zero neck weight | **0.021%** | rigid, as intended |
| jaw/neck blend band | 984 verts weighted to both head and neck | **82.4%** (water), 16.0% (walk) | **defect** |

The face core is rigid (0.017-0.021%) by every method — that part is settled.

The band figure is **not trustworthy**: the same band measures 190% (head bone
alone), 24% (a realistic 30 deg turn split across the chain), 80% and 946%
(face gate on two builds of the same clip). The band is also not a two-bone
blend -- `DEF-spine.005` carries 45% of its weight across 977 of 984 verts.

No weights were changed. Full investigation: `docs/JAW_NECK_FINDING.md`.

## 3. Watering-can prop

Still the diagnostic proxy (`NOT_FOR_SHIPPING`). A provenance-cleared mesh is
required before any water clip can be judged as final. The attachment contract
it must satisfy is recorded in `art/animation/v2/water_can/prop_attachment.json`.

## 4. Rodin character licence — RESOLVED (2026-08-21)

Recorded. Hyper3D Rodin, **paid Creator plan** (a subscription is required even
to download). ToS **§5(a)** — "we will not limit your use of such Output" — and
**§2** — export "for private or commercial use depending on your subscription
plan". Archived with hashes in `art/character/SOURCE_LICENSES.md` and
`art/character/licence_evidence/`.

Classified **`commercial_use: allowed (plan-dependent)`**, deliberately *not*
`copyright_ownership: transferred`: §5(a) is a covenant not to restrict, and §5
separately disclaims any warranty that Output is copyrightable or that IP rights
can be registered to anyone. Recording the stronger claim would assert something
the terms do not say.

Two risks recorded rather than resolved: the terms are **unversioned** ("Current
version", no date) so they can change silently — hence the dated snapshot; and
training-data provenance is unauditable, which §5 leaves with the user.
