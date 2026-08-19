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

### Where it applies — CORRECTED by runtime evidence

An earlier version of this document claimed, from a source grep, that
`nvdiffrast` appeared only in texturing/rendering modules and therefore did not
touch the geometry path. **That claim was wrong.**

A real inference run was instrumented to dump `sys.modules` after execution.
The modules actually loaded during *geometry* inference include:

```
_nvdiffrast_c   nvdiffrast   nvdiffrast.torch   nvdiffrast.torch.ops
o_voxel  o_voxel._C  cumesh  cumesh._C  flex_gemm  ...
```

The mechanism: **`o_voxel` — a core geometry extension — imports `nvdiffrast`
at import time.** Loading it is unavoidable; `import o_voxel` fails outright
with `ModuleNotFoundError: No module named 'nvdiffrast'` until nvdiffrast is
installed.

**Consequence:** every asset this pipeline produces is nvdiffrast-derived,
geometry included. The whole pipeline is therefore **research/evaluation
only**, not merely its textures. Evidence: `player_v01/logs/out/smoke_modules.json`.

A grep proves what a file mentions. It does not prove what a program loads.

### Additional gated / restricted dependency found at runtime

`briaai/RMBG-2.0` (background removal) is **gated** on Hugging Face — the
pipeline aborts with a 401 unless the account has accepted its terms — and is
itself **non-commercial**. Pixal3D constructs it unconditionally at pipeline
load, but `preprocess_image()` skips background removal when the input is RGBA
with a real alpha channel. Supplying alpha inputs and stubbing the constructor
avoids the gate and the extra licence entirely.

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

---

## Correction: the failed run used the wrong checkpoint

The first pilot ran Pixal3D's **code** against **microsoft/TRELLIS.2-4B**'s
**checkpoint**. `TencentARC/Pixal3D` weights (~24 GB) were never downloaded.

| Checkpoint | `ckpts/ss_flow_img_dit_1_3B_64_bf16.json` -> `image_attn_mode` |
|---|---|
| `TencentARC/Pixal3D` | `"proj"` — accepts the projected conditioning dict |
| `microsoft/TRELLIS.2-4B` | absent -> `"cross"` — expects a tensor |

That single difference produced `AttributeError: 'dict' object has no attribute
'type'`. **TRELLIS.2 is the code and dependency base, not a substitute for
Pixal3D's trained weights.** Future runs must pin `TencentARC/Pixal3D` by model
revision and use it as the generation checkpoint.

The nvdiffrast finding above is unaffected and still stands: the pipeline
output remains evaluation-only.

**Confirmed by run 2 (instance 48073234).** With `TencentARC/Pixal3D`'s own
weights, all four flow models report `image_attn_mode == "proj"`, the
projection path constructs, and the `'dict' object has no attribute 'type'`
error does not occur. That run failed later and for an unrelated reason (a
missing `einops` in a `torch.hub` dependency), so it says nothing about output
quality — but the checkpoint diagnosis is settled.

Run 2 also reconfirms the nvdiffrast position: `_nvdiffrast_c`, `nvdiffrast`
and `nvdiffrast.torch` appear in the runtime module dump alongside `o_voxel`
and `cumesh`. Evidence: `player_v01/out/run2_modules.json`.
