# AI generation stack — licence and provenance audit

Audited 2026-08-18 for the Red Valley player-character pilot.
Compute: Vast.ai instance `48000390`, A100 SXM 80 GB PCIe, driver 595.71.05,
torch 2.5.1+cu124, sm_80.

**Status of everything produced with this stack: EVALUATION ONLY.**
See `art/character/ai_generated/EVALUATION_ONLY.md`.

---

## Code repositories (pinned)

| Repository | Pinned commit | Licence | Default branch |
|---|---|---|---|
| [QwenLM/Qwen-Image](https://github.com/QwenLM/Qwen-Image) | `6b5e1f5cec98` | **Apache-2.0** | main |
| [TencentARC/Pixal3D](https://github.com/TencentARC/Pixal3D) | `cdbb2bbffbf4` | **MIT** | master |
| [microsoft/TRELLIS.2](https://github.com/microsoft/TRELLIS.2) | `75fbf0183001` | **MIT** | main |
| [VAST-AI-Research/SkinTokens](https://github.com/VAST-AI-Research/SkinTokens) | `273b691d3598` | **MIT** | main |

## Checkpoints (weights) — audited separately from the code

A repository licence does not automatically cover its weights, so each was
checked on its own model card:

| Checkpoint | Licence tag | Gated | Size on disk |
|---|---|---|---|
| [Qwen/Qwen-Image-Edit-2511](https://huggingface.co/Qwen/Qwen-Image-Edit-2511) | `license:apache-2.0` | no | 54 GB |
| [microsoft/TRELLIS.2-4B](https://huggingface.co/microsoft/TRELLIS.2-4B) | `license:mit` | no | 16 GB |
| [VAST-AI/SkinTokens](https://huggingface.co/VAST-AI/SkinTokens) | `license:mit` | no | 1.6 GB |
| [Qwen/Qwen-Image-2512](https://huggingface.co/Qwen/Qwen-Image-2512) | `license:apache-2.0` | no | not downloaded — the brief prefers concept-guided editing, so only the Edit model was needed |

All weights are permissive and ungated. **The restriction below comes from
rendering dependencies, not from any model or checkpoint.**

---

## The commercial-use restriction

TRELLIS.2 (and therefore Pixal3D, which builds on it) depends on:

| Dependency | Licence | Commercial use |
|---|---|---|
| [NVlabs/nvdiffrast](https://github.com/NVlabs/nvdiffrast) | Nvidia Source Code License (1-Way Commercial) | **NO** |
| [NVlabs/nvdiffrec](https://github.com/NVlabs/nvdiffrec) | Nvidia Source Code License | **NO** |

Despite the name "1-Way Commercial", §3.3 reads:

> *"The Work and any derivative works thereof only may be used or intended for
> use **non-commercially**. The Work or derivative works thereof may be used or
> intended for use by Nvidia or its affiliates commercially or
> non-commercially. As used herein, 'non-commercially' means for **research or
> evaluation purposes only**."*

The commercial permission runs **one way — to NVIDIA**, not to licensees.

### Where it actually applies (verified by source inspection)

`nvdiffrast` is imported in exactly these places:

```
Pixal3D/pixal3d/pipelines/trellis2_texturing.py     <- texturing
Pixal3D/pixal3d/renderers/mesh_renderer.py          <- rendering
Pixal3D/pixal3d/renderers/pbr_mesh_renderer.py      <- PBR rendering
TRELLIS.2/trellis2/pipelines/trellis2_texturing.py  <- texturing
TRELLIS.2/trellis2/renderers/mesh_renderer.py       <- rendering
```

It is **not** imported by `Pixal3D/inference.py`, the geometry-generation
entry point. TRELLIS.2's `setup.sh` likewise treats `--nvdiffrast` and
`--nvdiffrec` as *optional* flags.

**Consequence — a real distinction, not a technicality:**

- **Raw geometry** produced by the shape pipeline does not pass through
  `nvdiffrast`.
- **PBR textures** produced by the texturing pipeline **do**.

Since the brief requires 4K PBR textures, the delivered asset is
texturing-derived and therefore **non-commercial**. If a licence-clean asset
is ever needed, the untextured mesh is the cleaner starting point — but that
is a decision for a human, and this note is not legal advice.

---

## Other dependencies pulled in

`MoGe` (github.com/microsoft/MoGe, via Pixal3D `requirements.txt`) — MIT.
Standard PyPI packages (diffusers, transformers, trimesh, kornia, timm,
plyfile, opencv-python-headless) — Apache-2.0/MIT/BSD.

`flash-attn`, `cumesh`, `o_voxel`, `flexgemm` are build-time CUDA extensions
required by TRELLIS.2; they affect performance, not asset licensing.

## Reproducing this audit

```bash
tools/assetgen/audit_licenses.sh     # re-queries GitHub + HF APIs
```
