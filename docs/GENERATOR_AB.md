# Generator A/B: ARDY vs Kimodo — setup, licences, and a blocking finding

Status: **contracts built and proven for both; Kimodo generation blocked by local
hardware.** No clip promoted, no winner declared, **$0 spent**.

## Pins and licences

Full record: `art/animation/kimodo/LICENSES.md`.

| component | pin |
|---|---|
| `nv-tlabs/kimodo` | commit `1aece8c124d73d255ceff5086d983b844c9f4e94` — Apache-2.0 |
| `nvidia/Kimodo-SOMA-RP-v1.1` | revision `6c9233af1180b8151e3c4703477104af5dce9dd5` — NVIDIA Open Model License |
| `nv-tlabs/ardy` | commit `693f74d13b3d04a0a22ce127ee79c929dd89756b` — Apache-2.0 |
| `nvidia/ARDY-Core-RP-20FPS-Horizon40` | revision `abe6c43beb28c867c950acb824b9c4ef3d63fb76` — NVIDIA Open Model License |
| text encoder (both) | Llama 3 + LLM2Vec — Meta Llama 3 Community License + MIT |

**Skeleton asserted, not assumed.** `Kimodo-SOMA-RP-v1.1` uses **SOMASkeleton30**,
verified from the checkpoint: `stats/motion/body/mean.npy` is `(364,)` and
`30·3 + 30·6 + 30·3 + 4 = 364`; a 77-joint representation would be 928. The
adapter re-checks this at load time and refuses a mismatch.

## The contract is body-relative, and that mattered

`tools/rvmotion/build_water_contract.py` emits the same contract through each
generator's own constraint classes. Three things had to be normalised or the A/B
would have been decided by something other than generator quality:

| stated in absolute terms | why that breaks the comparison |
|---|---|
| frame indices | ARDY Core runs at **20 fps**, Kimodo-SOMA at **30**. Fixed frame numbers would give them different requests. Windows are defined in **seconds**. |
| spout height, stagger | the skeletons differ in size, so the same world target is a different task. Everything scales by hip height against the **shipping character**. |
| trunk lean cap | see below — capping it made the contract *impossible* for one generator and trivial for the other |

## Blocking finding: ARDY's Core27 must bow; Kimodo's SOMA30 need not

To place the same fixed-size watering can's spout at the same body-relative depth
over the bed:

| | ARDY Core27 | Kimodo SOMA30 |
|---|---|---|
| standing height | 1.626 m | 1.536 m |
| shoulder height | 1.422 m | 1.367 m |
| arm length | 0.528 m | 0.559 m |
| **shoulder ÷ arm** | **2.69** | **2.45** |
| lowest grip, straight arm, upright | 0.894 m | 0.808 m |
| **minimum trunk lean to reach the target** | **54°** | **6°** |

The pour needs a grip at roughly **0.81 m** (the can's spout hangs 0.316 m below
the grip at a 44° tilt, and the prop is a fixed real size that does not scale with
the skeleton). That is *below* what ARDY's Core27 can reach with a straight arm
from an upright shoulder, and *just within* SOMA30's.

**This explains the bowing in the existing ARDY clip.** It was never a bad prompt
or a retarget defect: Core27's proportions physically require a deep trunk hinge
to bring a fixed-size can near the ground. The earlier clip's 23° lean was not
enough, which is exactly why its spout sat 0.39 m above the bed.

An earlier draft of this contract capped lean at 12°, which silently made the
task impossible for ARDY and easy for Kimodo. Lean is now a **measured outcome**,
not an input: *reaching the same target with less trunk hinge is the better
result*, and on anthropometry alone Kimodo's skeleton starts ahead.

## Contract corrections (review round)

Four problems found in the first contract, all confirmed and fixed:

| problem | fix |
|---|---|
| the builder searched the band from the shallowest end and broke on the first feasible point, so both generators were quietly asked for **0.30 m** while the written contract says the **0.22 m midpoint** | the documented 0.22 m is asked for directly; escalation away from it is explicit and reported, never silent |
| **dense conditioning** — 22 hand, 72 rear-foot, 42 landed-foot frames, against Kimodo's guidance of <20 per type | sparse keyframes: **3–6 per set, 21 total**, with an assertion that refuses ≥20 |
| the 54° figure assumed the shoulder could only be lowered by **trunk lean** | the solver now allows up to 10 cm of **pelvis drop** (knee flexion), and a sparse hips constraint carries it, so bowing is not the only lever |
| no pelvis target existed | `HipsConstraintSet` on 3 pour keyframes |

**Allowing knee flexion sharpens the anthropometry finding rather than softening
it.** Reaching the documented 0.22 m target:

| | trunk lean | pelvis drop |
|---|---|---|
| ARDY Core27 | **46°** | 0.094 m |
| Kimodo SOMA30 | **0°** | 0.099 m |

Kimodo's skeleton reaches the target with **no trunk bow at all**, using knee
flexion alone. ARDY's still needs a 46° hinge.

## Two scorecards, not one

`tools/rvmotion/scorecard.py`. A single number would conflate two different
questions, and the conflation is the whole problem here:

- **A — morphology-normalised generator quality.** Did the model satisfy the
  contract *in its own body*? Measured on the native output before retargeting,
  in arm lengths, hip heights and degrees, so skeleton size cancels. This is the
  fair generator comparison.
- **B — production result.** What the player sees: retargeted onto the Rigify
  character with the fixed shipping can, in absolute metres against the game's
  contract. Anthropometry deliberately does *not* cancel here.

## Kimodo generation: blocked on local memory, not on anything else

Everything up to generation works: repo pinned, checkpoint pinned, adapter
written and verified, contract built (4 constraint sets, 149 constrained frames,
72 frames @ 30 fps, 98% arm extension at 6° lean).

Kimodo requires the **LLM2Vec / Llama-3-8B** text encoder, loaded in **bfloat16**
(~16 GB). This workstation has **15 GB RAM and 11.6 GB VRAM**:

| attempt | result |
|---|---|
| `TEXT_ENCODER_DEVICE=cpu` (NVIDIA's documented small-VRAM route) | terminated by `systemd-oomd`, exit 143 — bf16 8B needs ~16 GB RAM, machine has 15 GB total |
| `device="auto"` (shard GPU + CPU) | `torch.OutOfMemoryError` — filled 10.3 GB of 11.6 GB VRAM and could not allocate 112 MiB more |

NVIDIA's `<3 GB VRAM` claim for `TEXT_ENCODER_DEVICE=cpu` is about **VRAM**; it
moves the 16 GB cost onto system RAM, which this box does not have either.

### Options, for decision

| option | cost | confounds the A/B? |
|---|---|---|
| **A. 4-bit quantized text encoder** (~5.5 GB, fits the 3060) | needs a small change to Kimodo's encoder loading | changes text-embedding numerics — a real, if modest, confound |
| **B. Run `kimodo_textencoder` on a machine with ≥24 GB**, point `generate.py` at its URL | free if such a machine exists | no |
| **C. Add RAM** (32 GB) and use the documented CPU route | hardware | no |
| **D. Cloud GPU with ≥24 GB VRAM** | paid — needs a cap | no |

**Prompt-embedding cache.** `tools/rvmotion/cache_prompt_embedding.py` saves the
bf16 embedding from one clean encoder load. The encoder exists only to turn a
prompt into a fixed-size vector; the motion model itself runs on the 3060 easily.
Caching it on the run that can afford the encoder should let subsequent local
generations skip Llama-3-8B entirely. The cache is keyed on the exact prompt
text, so an edited prompt cannot silently reuse a stale vector.

**Not attempted:** patching Kimodo's loader. That would be modifying upstream
inference behaviour in the middle of a generator comparison, which is exactly
what makes a comparison untrustworthy.

## ARDY under the revised contract

The revised ARDY contract is **built and ready** (`art/animation/ardy_pilot/
constraints_v2/water_contract.json`, 4 sets, 100 constrained frames, 48 frames
@ 20 fps). ARDY has the identical text-encoder requirement, so it is blocked
locally for the same reason.

**Estimated cloud cost for one ARDY candidate**, from the previous measured run:
RTX 3090 at ~$0.156/h, ~22 min wall clock end to end (install, ~20 GB prefetch,
generation) ≈ **$0.06**, with a **$0.10 cap** and the existing watchdog. Not
started — the standing instruction is to stop before creating any paid instance
and report the required cap.
