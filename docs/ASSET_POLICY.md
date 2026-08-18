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

## The commercial-asset gate

The policy above governs what an agent may *do*. This section governs what may
*ship*, and unlike the rest of the document it is enforced by a program:
`tools/asset_gate.py`, run by `tools/verify.sh` and by GitHub Actions before
every release export.

It is **fail-closed**. Silence is never consent:

| Situation | Result |
|---|---|
| Production file with no manifest entry | **blocked** |
| `commercial_status` missing, `unknown`, or a value the gate doesn't recognise | **blocked** |
| Any dependency licence with `commercial_use: false` | **blocked** |
| File changed since it was cleared (sha256 mismatch) | **blocked** |
| Scene, script or `.import` referencing an evaluation-only path | **blocked** |
| Export preset that doesn't exclude the evaluation roots | **blocked** |
| Built package containing an evaluation-only path | **blocked** |
| Missing `.gdignore` or `EVALUATION_ONLY.md` in an evaluation root | **blocked** |

### The manifest

`asset_provenance.json` records, for every file under a production root
(`assets/`): `source`, `generator`, `dependency_licences` (each with an
explicit `commercial_use` boolean and an evidence URL), `evidence_urls`,
`commercial_status`, and the `sha256` of the cleared bytes.

The hash is what makes clearance mean something. A clearance applies to the
bytes a person reviewed, not to the filename — replace the file and the gate
demands a fresh clearance.

Entries seeded when the gate was introduced carry `clearance.method:
"baseline"`: provenance derived from the repository rather than an individual
sign-off. They pass, and `check --strict-baseline` lists them so the backlog
stays visible.

### Promotion — the only route from evaluation to production

```bash
tools/asset_gate.py promote art/character/ai_generated/player_v01/processed/x.glb \
    assets/models/x.glb \
    --source "..." --generator "..." \
    --dep "component|licence|true|https://evidence" \
    --evidence-url https://... --cleared-by "Name" \
    --evidence "what was reviewed and how" --cleared-on 2026-08-18
```

**An agent must never set an asset's status to `cleared`.** The command
enforces this as far as a program can: it refuses without a named person,
written evidence and an evidence URL; it refuses outright if any dependency
forbids commercial use; and it takes its confirmation from `/dev/tty`, which a
piped or automated caller has no way to answer. That is a real barrier, not a
complete one — anyone can still hand-edit JSON. The manifest is small and
diffable precisely so that a status change is obvious in review. **A change to
`commercial_status` is a human decision and should be reviewed as one.**

### The specific thing being guarded

`art/character/ai_generated/` holds AI-pipeline evaluation output. Its
rendering dependencies (NVIDIA `nvdiffrast` / `nvdiffrec`) are under the
*Nvidia Source Code License (1-Way Commercial)*, whose §3.3 limits **our** use
to research or evaluation — the commercial permission is NVIDIA's, not ours.
Clearing any of it requires either confirming `nvdiffrast` is absent from the
asset-producing path, or a legal review. Until then it is walled off:
`.gdignore` (Godot won't import it), gitignored (won't enter history),
excluded from every export preset, and checked for in the built package.

## Working agreement

- Human authors or sources the asset. Agent imports, fits, validates, renders,
  exports.
- Agent stops for human approval at visual milestones — no autonomous
  "continue until it passes" loops.
- Agent reports defects plainly, including ones that make its own work look
  bad, and never substitutes metrics for looking at the render.
