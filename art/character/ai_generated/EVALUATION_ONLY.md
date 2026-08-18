# EVALUATION ONLY — not cleared for shipping

Everything under `ai_generated/` is **research / evaluation output** and must
not be shipped in a commercial build or copied into the Godot `assets/` tree.

**Why:** the generator stack (Pixal3D → TRELLIS.2) depends on NVIDIA
`nvdiffrast` / `nvdiffrec`. Their licence is the *Nvidia Source Code License
(1-Way Commercial)*; despite the name, §3.3 limits **our** use to
"research or evaluation purposes only" — the commercial permission is
NVIDIA's, not the licensee's.

Model code and checkpoints themselves are permissive (Apache-2.0 / MIT) — see
`art/character/AI_MODEL_LICENSES.md`. The restriction comes from the
rendering/PBR dependencies, not the weights.

Clearing this for production requires either confirming `nvdiffrast` is absent
from the asset-producing path, or a legal review.
