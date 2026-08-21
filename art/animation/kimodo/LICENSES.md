# Kimodo benchmark — licence and provenance record

Pinned before any generation. Nothing here is promoted to `assets/`.

| component | pin | licence | commercial |
|---|---|---|---|
| `nv-tlabs/kimodo` code | commit **`1aece8c124d73d255ceff5086d983b844c9f4e94`** (2026-07-13) | **Apache-2.0** (`LICENSE` in repo root) | yes |
| `nvidia/Kimodo-SOMA-RP-v1.1` checkpoint | revision **`6c9233af1180b8151e3c4703477104af5dce9dd5`** | **NVIDIA Open Model License** (`license_name: nvidia-open-model-license`) | yes, per NVIDIA's model card |
| `meta-llama/Meta-Llama-3-8B-Instruct` | gated (manual approval, granted to this account) | **Meta Llama 3 Community License** | conditional — see note |
| `McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp` | latest | **MIT** (adapter weights); inherits Llama 3 terms for the base | conditional |
| `McGill-NLP/…-mntp-supervised` | latest | **MIT**; inherits Llama 3 terms | conditional |

## Notes that matter for shipping

- The **text encoder is a dependency of generation, not of the output.** Llama 3
  terms govern use of the encoder; the motion produced is governed by the Kimodo
  checkpoint's licence. This distinction should be confirmed with a human before
  any generated clip is shipped.
- **Meta Llama 3 Community License** carries an acceptable-use policy and a
  700M-MAU threshold clause. Not a blocker at this scale, but it is a licence the
  project now depends on for *producing* animation and must appear in any
  dependency audit.
- Same standing blocker as before: **the Rodin character's own licence is still
  unrecorded**, and that blocks promotion regardless of what the generator
  licences say.

## Skeleton assertion (not assumed)

`Kimodo-SOMA-RP-v1.1` uses **SOMASkeleton30**, verified from the checkpoint
itself: `stats/motion/body/mean.npy` is `(364,)`, and 30 joints give
`30·3 + 30·6 + 30·3 + 4 = 364`. A 77-joint representation would be 928. The
adapter asserts this at load time rather than trusting the model name.
