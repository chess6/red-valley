# Player v01 — run 2 (corrected checkpoint), 1024 candidate

**EVALUATION ONLY.** The pipeline loads `nvdiffrast` through the `o_voxel`
geometry extension, so every output is nvdiffrast-derived and non-commercial.
See `art/character/AI_MODEL_LICENSES.md` and `EVALUATION_ONLY.md`.

## What run 1 got wrong, and how run 2 fixes it

Run 1 executed Pixal3D's **code** against **microsoft/TRELLIS.2-4B**'s
**weights**. TRELLIS.2 is the code and dependency base, not a substitute for
Pixal3D's trained checkpoint. The sparse-structure flow model config differs:

| Checkpoint | `ss_flow_img_dit_1_3B_64_bf16.json` → `image_attn_mode` |
|---|---|
| `TencentARC/Pixal3D` | `"proj"` — accepts the projected conditioning dict |
| `microsoft/TRELLIS.2-4B` | absent → defaults `"cross"` — expects a tensor |

Hence `AttributeError: 'dict' object has no attribute 'type'`. Nothing was
patched to work around it; the correct weights were downloaded instead.

## The gate

Before any GPU is spent, the run asserts `image_attn_mode == "proj"` on every
flow model and stops if it does not hold. Observed on the pinned checkpoint:

| Config | Model | `image_attn_mode` |
|---|---|---|
| `ss_flow_img_dit_1_3B_64_bf16.json` | SparseStructureFlowModel | `"proj"` |
| `slat_flow_img2shape_dit_1_3B_1024_bf16.json` | ElasticSLatFlowModel | `"proj"` |
| `slat_flow_img2shape_dit_1_3B_512_bf16.json` | ElasticSLatFlowModel | `"proj"` |
| `slat_flow_imgshape2tex_dit_1_3B_1024_bf16.json` | ElasticSLatFlowModel | `"proj"` |

VAE decoders carry no `image_attn_mode`; they are not flow models and are not
gated.

## Pins

| Thing | Pin |
|---|---|
| Checkpoint | `TencentARC/Pixal3D` rev `0b31f9160aa400719af409098bff7936a932f726` (23 GB) |
| Pixal3D code | `cdbb2bbffbf4` |
| TRELLIS.2 code | `75fbf0183001` |
| torch | 2.6.0+cu124, `TORCH_CUDA_ARCH_LIST=8.0`, `ATTN_BACKEND=sdpa` |

## Input

`reference/front_ref_rgba1024.png` — RGBA, 1024×1024, sha256
`7fb273c136bb43c99c372c63c07db36b2f3c1d770caba390bd341d60f991af6b`.

The earlier `front_ref_rgba.png` was RGB in spite of its name. Alpha is not
cosmetic here: `preprocess_image()` only skips background removal for RGBA
input with a real alpha channel, and the background remover is the **gated,
non-commercial** `briaai/RMBG-2.0`. The matte is a border-connected flood fill
of the pure-black background rather than a global threshold, so dark boots and
hair are not punched through.

**Source-limited, as agreed.** Judge broad geometry, outfit recognition, rear
completion and pipeline viability only — not facial, fabric or pore-level
detail, and do not treat this as Pixal3D's quality ceiling.

## Result — no GLB. Stopped, per "no automatic second rental if anything fails".

Instance `48073234` (A100 SXM4 80 GB, $1.328/h), destroyed. Account verified
empty afterwards: 0 instances, nothing billing.

| Phase | Outcome |
|---|---|
| Provisioning | one contract, adopted atomically |
| Install + 23 GB download | **15 min**, all extensions built |
| Import check | `cumesh` `o_voxel` `flex_gemm` `natten` `nvdiffrast.torch` `diffusers` `trimesh` — all ok |
| `image_attn_mode == "proj"` gate | **passed** on all 4 flow models |
| Pipeline construction | got as far as `DinoV3ProjFeatureExtractor` |
| Inference | **failed after 137.8 s**, before generating geometry |

### What failed

```
File ".../pixal3d/trainers/flow_matching/mixins/image_conditioned_proj.py", line 420, in _load_naf
    self.naf_model = torch.hub.load(...)          # valeoai/NAF
  File "/workspace/torch/hub/valeoai_NAF_main/src/model/jafar.py", line 4
    from einops import rearrange
ModuleNotFoundError: No module named 'einops'
```

A missing pip package in a `torch.hub` repo, not a model, checkpoint or
conditioning problem.

### What this run does establish

The checkpoint diagnosis was right. Run 1 died inside the *first* flow model
with `'dict' object has no attribute 'type'`. With `TencentARC/Pixal3D`'s own
weights the projection path constructs cleanly and that error is gone —
`image_attn_mode == "proj"` on every flow model, and the image-conditioning
stack builds. The pipeline reached a strictly later stage.

It establishes nothing about output quality: no geometry was generated.

The nvdiffrast finding is reconfirmed, not weakened. `run2_modules.json` shows
`_nvdiffrast_c`, `nvdiffrast`, `nvdiffrast.torch` loaded at runtime alongside
`o_voxel` and `cumesh`. Output remains evaluation-only.

### Fixed for the next attempt (not yet run)

`einops` added to the install phase, and the NAF upsampler is now preloaded
**during install** rather than at pipeline construction. That is the real
lesson: NAF is fetched from `torch.hub` when the pipeline is built, so its
dependencies were only exercised once the GPU was already billing. Preloading
moves that whole class of failure into the free phase.

### Cost

$0.51 of the $2 / 2 GPU-hour cap. 0.38 h billed. Balance $10.93 → $10.42.


---

# Run 3 — final controlled 1024 retry: no GLB, stopped at preflight

Instance `48075583` (A100 SXM4 80 GB, $1.068/h offer, $1.094/h actual, 100 GB
disk), offer `43131370`, destroyed. Account verified empty afterwards.

**Elapsed 0.31 h. Cost $0.41** of the $1.00 cap. Balance $10.42 -> $10.01.
One rental. **Zero generation attempts** — the run never reached inference.

## What the preflight caught

`einops` was fixed and NAF now preloads during install, so the run got past
run 2's failure. Installation, all four CUDA extension builds and all seven
imports succeeded. `pip check` passed. NAF loaded. Then, executing a real
tensor through NAF:

```
File "/workspace/torch/hub/valeoai_NAF_main/src/layers/attentions.py", line 72, in forward
    out = na2d(q, k, v, kernel_size=self.kernel_size, dilation=dilation, stride=1, backend="cutlass-fna")
File ".../natten/backends/configs/checks.py", line 520, in can_run_cutlass_fna
    target_fn("Can't run CUTLASS FNA; NATTEN was not built with libnatten.")
RuntimeError: Can't run CUTLASS FNA; NATTEN was not built with libnatten.
```

`natten 0.21.7` from PyPI is installed **without `libnatten`** — the compiled
CUTLASS kernels are absent (`from natten import has_bfloat16` also fails).
NAF's upsampler calls `na2d(..., backend="cutlass-fna")`, and Pixal3D calls NAF
during image conditioning, so generation could not have succeeded.

## Why this matters more than the run failing

An import check passes here: `import natten` succeeds, and run 2's install
verification reported `ok natten`. Only *executing a tensor* exposes it. The
requirement to run a real tensor through NAF rather than importing it is
precisely what turned a mid-generation failure into a preflight failure, at
$0.41 and with no wasted generation.

The same applies to why the probe initially failed on my side: NAF is
`forward(image, features, output_size, ...)` and `output_size` is a required
positional, so my first four guessed calls raised `TypeError`. That was a
defect in the check, corrected before the real finding surfaced.

## The fix — recorded, NOT run

`natten` must come from the wheel index carrying the compiled library:

```
pip install natten==0.21.7+torch260cu124 -f https://shi-labs.com/natten/wheels/
```

Written into `run3_remote.sh`. **No further rental has been started.**

## Still unknown

Output quality. Three runs in, no geometry has ever been generated, so nothing
about Pixal3D's results has been observed. Runs 2 and 3 each cleared the
previous blocker and stopped at the next one:

| Run | Cost | Reached | Stopped by |
|---|---|---|---|
| 1 | $2.10 | first flow model | wrong checkpoint (TRELLIS.2-4B weights) |
| 2 | $0.51 | pipeline construction | missing `einops` in a torch.hub repo |
| 3 | $0.41 | preflight, pre-inference | `natten` without `libnatten` |
