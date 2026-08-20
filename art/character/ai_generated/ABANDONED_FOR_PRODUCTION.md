# ABANDONED_FOR_PRODUCTION — Pixal3D / TRELLIS.2 image-to-3D pilot

**Status: ABANDONED FOR PRODUCTION. Closed 2026-08-19. Do not resume without
explicit approval.**

This directory is an **archived evaluation**. Nothing in it is a production
asset, a candidate for one, or a starting point for cleanup, rigging, retopo or
LOD work.

## Why it was abandoned

**1. Zero generated assets.** Across three paid runs the pipeline never
produced a single mesh. No geometry was ever generated, so nothing is known
about its output quality — this is not a judgement that the results were poor;
there are no results.

**2. Dependency-fragile.** Each run cleared the previous blocker and stopped at
the next one, every time in the dependency stack rather than the model:

| Run | Cost | Reached | Stopped by |
|---|---|---|---|
| 1 | $2.10 | first flow model | wrong checkpoint — Pixal3D code against `microsoft/TRELLIS.2-4B` weights (`image_attn_mode` defaults `"cross"`, expects a tensor, got a dict) |
| 2 | $0.51 | pipeline construction | `ModuleNotFoundError: No module named 'einops'` inside the `valeoai/NAF` torch.hub repo |
| 3 | $0.41 | preflight, before inference | `natten` installed without `libnatten`; NAF's `na2d(backend="cutlass-fna")` cannot run |

Three consecutive blockers, none of them the model, is the finding. The last
one is instructive: `import natten` succeeds and an import check reports it
healthy — only executing a tensor through NAF exposes it.

**3. Output would be commercially unusable regardless.** `nvdiffrast` is
imported by `o_voxel`, a **core geometry extension**, so it is loaded during
geometry inference and not merely for texturing. Under the Nvidia Source Code
License (1-Way Commercial) §3.3 the commercial permission runs one way — to
NVIDIA — and licensees get "research or evaluation purposes only". Anything
this pipeline produces is therefore evaluation-only **including its geometry**.
Establishing this took runtime evidence: an earlier claim based on a source
grep was wrong and was retracted. A grep proves what a file mentions; it does
not prove what a program loads. Evidence: `player_v01/out/run2_modules.json`,
`player_v01/logs/out/smoke_modules.json`.

Point 3 stands on its own: even a fully working pipeline could not have shipped
into Red Valley.

## Cost ledger

| Item | Cost |
|---|---|
| Run 1 pilot + earlier aborts | ~$2.34 |
| Orphaned-instance incident (create reported `success:false`, left two contracts) | $0.74 |
| Run 2 (instance `48073234`, A100 SXM4, $1.328/h) | $0.51 |
| Run 3 (instance `48075583`, A100 SXM4, $1.094/h) | $0.41 |
| **Total** | **~$4.00** |

Balance at close: **$9.99**, against a $6.00 stop line and the $5.00
auto-refill floor. The floor was never approached.

## Pinned revisions (as evaluated)

| Component | Pin | Licence |
|---|---|---|
| `TencentARC/Pixal3D` (code) | `cdbb2bbffbf4` | MIT |
| `TencentARC/Pixal3D` (weights, 23 GB) | rev `0b31f9160aa400719af409098bff7936a932f726` | MIT |
| `microsoft/TRELLIS.2` (code/dependency base) | `75fbf0183001` | MIT |
| `QwenLM/Qwen-Image` | `6b5e1f5cec98` | Apache-2.0 |
| `VAST-AI-Research/SkinTokens` | `273b691d3598` | MIT |
| `NVlabs/nvdiffrast` | v0.4.0 | **Nvidia Source Code License — non-commercial** |
| `briaai/RMBG-2.0` | — | **gated, non-commercial** (stubbed; never invoked) |
| torch | 2.6.0+cu124, `TORCH_CUDA_ARCH_LIST=8.0`, `ATTN_BACKEND=sdpa` | — |

Full audit: `art/character/AI_MODEL_LICENSES.md`.

## What is preserved

| Where | What |
|---|---|
| `tools/assetgen/*.sh`, `*.py` | provisioning, spend guard, watchdog, remote recipes, preflight, generation driver, review renders |
| `tools/tests/test_provision.py`, `test_budget.py` | 93 passing regression tests for the cost-control machinery |
| `player_v01/logs/` | install, build and inference logs from every run |
| `player_v01/logs/run3_natten_traceback.txt` | the final blocker's full traceback |
| `player_v01/out/run2_modules.json` | runtime module trace proving nvdiffrast in the geometry path |
| `player_v01/RUN2_MANIFEST.md` | per-run detail for runs 2 and 3 |
| `player_v01/reference/` | input reference; the run-3 input was `front_ref_rgba1024.png`, sha256 `7fb273c136bb43c99c372c63c07db36b2f3c1d770caba390bd341d60f991af6b` (binaries not committed) |

## What outlives the pilot

The cost-control tooling is independent of Pixal3D and stays in service: the
spend guard, the account watchdog, and `provision.py`'s atomic create — which
exists because `vastai create` reported `success:false` while leaving two live
contracts, and one billed unwatched. Those parts earned their keep.
