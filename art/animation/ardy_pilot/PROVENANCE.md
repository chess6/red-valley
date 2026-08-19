# ARDY motion pilot — provenance and licence audit

Audited 2026-08-19, before any generation. Result: **no licence blocker for
ARDY itself**; two practical constraints and one attribution obligation.

## Pinned components

| Component | Pin | Licence |
|---|---|---|
| ARDY code — `github.com/nv-tlabs/ardy` | `693f74d13b3d04a0a22ce127ee79c929dd89756b` | **Apache-2.0** |
| Checkpoint `nvidia/ARDY-Core-RP-20FPS-Horizon40` | `abe6c43beb28c867c950acb824b9c4ef3d63fb76` | NVIDIA Open Model Agreement, **ungated** |
| Text encoder `meta-llama/Meta-Llama-3-8B-Instruct` | `8afb486c1db24fe5011ec46dfbe5b5dccdb575c2` | **llama3**, `gated: manual` |
| LLM2Vec (vendored in `ardy/model/llm2vec`) | per ATTRIBUTIONS.MD | **MIT** (McGill-NLP) |
| Unitree mujoco (G1 variant only) | per ATTRIBUTIONS.MD | BSD 3-Clause |
| MotionCorrection (`MotionCorrection/`) | same repo commit | Apache-2.0 (repo licence) |

Checkpoint facts, read from the model card and LICENSE directly:
- *"This model is ready for commercial or non-commercial use."*
- Open Model Agreement: *"Models are commercially usable"*, *"NVIDIA does not
  claim ownership to any outputs generated using the Models"*.
- Architecture: 326 M params, two-stage transformer diffusion, **CoreSkeleton27**,
  20 FPS, 40-frame horizon (2.0 s per generation).

**This is not another nvdiffrast.** That licence granted commercial rights one
way — to NVIDIA — and sat in the geometry path. ARDY grants them to us and
disclaims output ownership.

## Attribution obligation (Llama)

The text encoder is Llama 3 under the **Llama 3 Community License**: commercial
use is permitted below 700 M MAU, but products built with it carry a
**"Built with Meta Llama 3"** attribution requirement. If ARDY-generated motion
ships in Red Valley, that notice belongs in the credits alongside the
CC-BY boots attribution.

Note the asymmetry: NVIDIA disclaims ownership of ARDY's *output*, but the
prompt is encoded by Llama, so the Llama terms attach to the pipeline.

## Practical constraints

| Constraint | Detail |
|---|---|
| **Llama gate is `manual`** | Meta approves by hand. The SPAR3D gate was `auto`; this one is not, so it may take hours or days |
| **Text encoder needs ~14 GB VRAM** in bfloat16 on cuda | The RTX 3060 has 12 GB. Upstream supports `cpu / bfloat16`, so **the encoder runs on CPU and ARDY on GPU** — slower prompt encoding, no rental needed |
| Supported hardware | Ampere is listed; RTX 3060 (sm_86) qualifies |
| Linux only | Matches this machine |

## Status

Generation has **not** started. Blocked on Llama-3-8B-Instruct access approval.
