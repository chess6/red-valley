# Asset policy — no LLM-authored art

**Rule: the Blender MCP connector is for pipeline automation, not for creating
art. An agent must not author models, garments, characters, grooms or sculpts.**

This is not a style preference. It is the conclusion of a long, well-documented
failure in this repo, summarised below so nobody has to repeat it.

---

## What an agent MAY do in Blender

Automation and verification — work with a deterministic right answer:

- **Import and fit** already-authored assets through their authored systems
  (e.g. MPFB's fitting for MakeHuman garments).
- **Batch operations**: renaming, assigning materials from a written spec,
  applying modifier stacks, generating LODs from an authored mesh, unit/scale
  conversion, transferring weights.
- **Validation**: non-manifold and boundary checks, intersection/penetration
  tests, symmetry measurement, triangle budgets, UV presence, missing-texture
  detection, naming conventions.
- **Rendering**: turnarounds, review sheets, contact sheets, screenshots,
  wireframe overlays — with fixed cameras and lighting.
- **Export**: GLB/glTF for Godot, import settings, file hygiene.
- **Provenance**: recording source URL, author, licence and SHA-256 for every
  third-party asset (see `art/character/SOURCE_LICENSES.md`).
- **Checkpointing**: incremental `.blend` snapshots, preserved comparisons.

## What an agent MUST NOT do

Authoring — work whose only correctness test is "does it look right":

- Generating organic or garment geometry procedurally: parametric surface
  grids, lofts, swept cross-sections, "pattern panel" shells.
- Booleans used to shape clothing or anatomy.
- **Coordinate-predicate vertex deletion** to carve a shape (`if v.co.z < k:
  delete`). This tears topology and produces ragged edges.
- Cloth / physics **parameter-tuning loops** aimed at achieving a look.
- Shrinkwrap projection used as a *modelling* operation.
- Sculpting, scripted retopology, hair grooming, procedural faces.
- Nudging vertices to "fix" an art problem.

**If a required asset does not exist: stop and report.** Propose sourcing it
(with a licence check) or ask for it. Never synthesise a substitute and never
present one as progress.

---

## Why — the evidence from this repo

Five attempts to produce one leather vest, all through the MCP connector:

| Version | Approach | Outcome |
|---|---|---|
| v02 | Scripted surface grid from body topology | Ragged armholes, inflated shell, "arm wings" |
| v03 | Flat pattern panels + cloth sewing springs | 4 sims, all tore. Final edge lengths median **24 mm** against an 11–18 mm design |
| v04 | Assembled quad shell + shrinkwrap + cloth relax | Shell fine; relax passes drove it through the shirt, then shredded it |
| v05 | Derived from an authored MPFB jacket | **Worked** — because the geometry was authored by a human |

Every failure was individually diagnosable and individually fixed; a new one
appeared each time. The one approach that produced an acceptable result was
the one that started from human-authored topology.

### Specific traps, recorded so they are not rediscovered

- `sewing_force_max = 0` means **unlimited** in Blender, not "off". It crushes
  panels instantly.
- Catmull-Clark subdivision **contracts** a surface; a garment shrinkwrapped
  with clearance then subdivided sinks back inside the body.
- Shrinkwrap `NEAREST_SURFACEPOINT` applied *after* subdivision snaps points to
  disparate parts of the target and tears the mesh into ribbons.
- Large pin displacements detonate the cloth solver.
- `BVHTree.find_nearest` sign tests are **unreliable on solidified garments**:
  the nearest surface is often the inner wall, whose normal points at the body,
  producing false "penetration" counts (987 reported vs 2 actually visible).
- Inferred, distance-based body masks delete the face. Body masking must use
  explicit, garment-specific, manually inspected vertex groups containing no
  neck, head, arm or hand vertices.
- An asset's own delete-group may span the entire head (`Delete.male_casualsuit01`
  reaches z = 1.669). Never apply one unscoped.

---

## The two process failures behind the technical ones

1. **Wrong gate order.** Non-manifold counts, symmetry and containment were
   checked *before* silhouette, fit and resemblance. A mesh can be perfectly
   manifold and still look like nothing. Correct order:

   **silhouette & resemblance → garment fit & construction → materials →
   topology → deformation → retopo/LOD/export**

2. **Builder and reviewer were the same agent.** That produces rationalisation:
   passing statistics get reported as progress while the render plainly fails.
   A human approves visual milestones. The agent states what it thinks is
   wrong, and does not certify its own work.

## Working agreement

- Human authors or sources the asset. Agent imports, fits, validates, renders,
  exports.
- Agent stops for human approval at visual milestones — no autonomous
  "continue until it passes" loops.
- Agent reports defects plainly, including ones that make its own work look
  bad, and never substitutes metrics for looking at the render.
