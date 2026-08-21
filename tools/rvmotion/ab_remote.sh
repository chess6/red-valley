#!/usr/bin/env bash
# One instance, both generators, one seed each, then destroy.
#
# Runs the IDENTICAL interaction contract through ARDY and Kimodo so the A/B is
# about the generators. Both need the LLM2Vec/Llama-3-8B encoder in bf16 (~16 GB),
# which is the only reason this is not local. The prompt embeddings are cached and
# fetched back so future local runs on the 3060 can skip the encoder entirely.
#
# The HF token arrives in the environment and is never echoed.
set -uo pipefail
W=/workspace; export HF_HOME=$W/hf
# Hugging Face's Xet transfer backend failed mid-prefetch on a fresh instance
# (xet_get raised inside new_file_download_group with ample disk free). Fall back
# to plain HTTP range downloads, which are slower but do not depend on the Xet
# CAS being reachable from an arbitrary rented host.
export HF_HUB_DISABLE_XET=1
export HF_HUB_ENABLE_HF_TRANSFER=0
mkdir -p $W/{logs,out,emb}
LOG=$W/logs/ab.log
step(){ echo "[$(date -u +%H:%M:%S)] == $*" | tee -a $LOG; }
die(){ echo "STOP: $*" | tee -a $LOG; echo "$*" > $W/logs/failed; exit 1; }

ARDY_SHA=693f74d13b3d04a0a22ce127ee79c929dd89756b
ARDY_CKPT=abe6c43beb28c867c950acb824b9c4ef3d63fb76
KIMODO_SHA=1aece8c124d73d255ceff5086d983b844c9f4e94
KIMODO_CKPT=6c9233af1180b8151e3c4703477104af5dce9dd5

PROMPT="A person stands beside a garden bed holding a watering can in the right hand, takes one short step forward with the left foot into a stagger, keeps the right foot planted behind as support, bends the knees to lower the body and extends the right arm down and forward over the bed, tipping the can to pour, keeping the back neutral rather than bending deeply at the waist, then settles."

[ -s $W/kimodo_contract.json ] || die "kimodo contract missing"
[ -s $W/ardy_contract.json ]   || die "ardy contract missing"

step "packages"
pip install -q --upgrade pip setuptools wheel >>$LOG 2>&1
# huggingface_hub is a transitive dep of the two repos, but authentication has to
# happen BEFORE the prefetch, so install it up front rather than relying on an
# install that has not run yet.
pip install -q "huggingface_hub>=0.24" >>$LOG 2>&1 || die "huggingface_hub install"
python - <<PY >>$LOG 2>&1 || die "hf auth"
import os; from huggingface_hub import login; login(token=os.environ["HF_TOKEN"]); print("ok")
PY

step "clone + install kimodo ($KIMODO_SHA)"
cd $W && [ -d kimodo ] || git clone -q https://github.com/nv-tlabs/kimodo.git
cd $W/kimodo && git checkout -q $KIMODO_SHA
pip install -q -e . >>$LOG 2>&1 || die "kimodo install"
pip install -q "peft==0.18.1" "accelerate==1.13.0" "numpy==1.26.4" >>$LOG 2>&1 || die "pins"

step "clone + install ardy ($ARDY_SHA)"
cd $W && [ -d ardy ] || git clone -q https://github.com/nv-tlabs/ardy.git
cd $W/ardy && git checkout -q $ARDY_SHA
pip install -q -e . >>$LOG 2>&1 || die "ardy install"

step "prefetch weights (xet disabled)"
python - <<PY >>$LOG 2>&1 || die "prefetch"
from huggingface_hub import snapshot_download as dl
dl("nvidia/Kimodo-SOMA-RP-v1.1", revision="$KIMODO_CKPT", max_workers=8)
dl("nvidia/ARDY-Core-RP-20FPS-Horizon40", revision="$ARDY_CKPT", max_workers=8)
for r in ["meta-llama/Meta-Llama-3-8B-Instruct",
          "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp",
          "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised"]:
    dl(r, max_workers=8)
print("prefetched")
PY

step "cache the bf16 prompt embedding (so the 3060 can skip the encoder later)"
cd $W/kimodo
python $W/cache_prompt_embedding.py save --src $W/kimodo --prompt "$PROMPT" \
  --out $W/emb >>$LOG 2>&1 || echo "(embedding cache failed; not fatal)" | tee -a $LOG

step "KIMODO: 2.4 s, seed 0, one sample, post-processing ON"
cd $W/kimodo
python kimodo/scripts/generate.py "$PROMPT" \
  --model kimodo-soma-rp --duration 2.4 --seed 0 --num_samples 1 \
  --constraints $W/kimodo_contract.json --output $W/out/kimodo_water \
  >$W/logs/kimodo_gen.log 2>&1 || die "kimodo generation"
grep -q "set of constraints" $W/logs/kimodo_gen.log || die "kimodo ignored the constraints"

step "ARDY: 2.4 s, seed 0, one sample, post-processing ON"
cd $W/ardy
python scripts/generate.py "$PROMPT" \
  --model core --duration 2.4 --seed 0 --num_samples 1 \
  --constraints $W/ardy_contract.json --output $W/out/ardy_water \
  >$W/logs/ardy_gen.log 2>&1 || die "ardy generation"
grep -q "set of constraints" $W/logs/ardy_gen.log || die "ardy ignored the constraints"

step "outputs"
ls -la $W/out $W/emb | tee -a $LOG
find $W/out -name '*.npz' -exec sha256sum {} \; | tee -a $LOG
date -u +%FT%TZ > $W/logs/done
step "AB_DONE"
