#!/usr/bin/env bash
# Corrected pilot run: Pixal3D CODE + Pixal3D WEIGHTS (the first run wrongly
# paired Pixal3D's code with microsoft/TRELLIS.2-4B's checkpoint, whose
# sparse-structure flow model omits image_attn_mode and so defaults to "cross"
# and expects a tensor -- producing 'dict' object has no attribute 'type').
#
# Hard gate: every flow model must report image_attn_mode == "proj" BEFORE any
# inference runs. If it does not, this script stops rather than burning GPU.
set -uo pipefail
W=/workspace
export HF_HOME=$W/hf TORCH_HOME=$W/torch
# separate statements: bash expands all words of an `export` before
# assigning any of them, so $CUDA_HOME is still unbound on one line
export CUDA_HOME=/usr/local/cuda
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
export TORCH_CUDA_ARCH_LIST="8.0" MAX_JOBS=32 PIP_NO_BUILD_ISOLATION=1
export ATTN_BACKEND=sdpa
PIXAL_REV="0b31f9160aa400719af409098bff7936a932f726"
PIXAL_SHA=cdbb2bbffbf4
TRELLIS_SHA=75fbf0183001
PHASE="${1:?phase: install | gen}"
mkdir -p $W/{logs,models,repos,out}
LOG=$W/logs/run3_$PHASE.log
step(){ echo "[$(date -u +%H:%M:%S)] == $*" | tee -a $LOG; }
die(){ echo "[$(date -u +%H:%M:%S)] STOP: $*" | tee -a $LOG; echo "$*" > $W/logs/run2_failed; exit 1; }

if [ "$PHASE" = "install" ]; then

step "system packages"
apt-get update -qq >>$LOG 2>&1
apt-get install -y -qq git git-lfs build-essential ninja-build cmake libgl1 \
  libglib2.0-0 libx11-6 wget curl xz-utils >>$LOG 2>&1
pip install -q --upgrade pip setuptools wheel ninja packaging psutil >>$LOG 2>&1
pip install -q "huggingface_hub>=0.34,<1.0" hf_transfer >>$LOG 2>&1
export HF_HUB_ENABLE_HF_TRANSFER=1

step "downloading TencentARC/Pixal3D pinned @ $PIXAL_REV  (NOT TRELLIS.2-4B)"
python - <<PY >>$LOG 2>&1 &
from huggingface_hub import snapshot_download
p=snapshot_download("TencentARC/Pixal3D", revision="$PIXAL_REV",
                    local_dir="$W/models/pixal3d", max_workers=16)
print("DONE", p)
PY
DL=$!

step "cloning repos at pinned commits"
cd $W/repos
[ -d Pixal3D ]  || git clone -q https://github.com/TencentARC/Pixal3D.git Pixal3D >>$LOG 2>&1
( cd Pixal3D && git checkout -q $PIXAL_SHA )
[ -d TRELLIS.2 ] || git clone -q --recursive https://github.com/microsoft/TRELLIS.2.git TRELLIS.2 >>$LOG 2>&1
( cd TRELLIS.2 && git checkout -q $TRELLIS_SHA && git submodule update --init --recursive >>$LOG 2>&1 )

step "python env (torch 2.6.0 cu124 first: one ABI for every extension)"
pip install -q torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124 >>$LOG 2>&1 || die "torch"
pip install -q -r $W/repos/Pixal3D/requirements.txt >>$LOG 2>&1 || die "pixal reqs"
pip install -q "huggingface_hub>=0.34,<1.0" >>$LOG 2>&1
pip install -q "git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8" >>$LOG 2>&1
# NATTEN from PyPI installs a Python-only package with no libnatten, so its
# CUTLASS neighborhood-attention kernels do not exist and NAF's upsampler --
# which Pixal3D calls during image conditioning -- raises at runtime. The
# prebuilt wheels matching this torch/CUDA pair carry the compiled library.
# NOT YET RUN: recorded as the fix, awaiting approval for another rental.
pip install -q pymeshlab xatlas pygltflib einops >>$LOG 2>&1
pip install -q natten==0.21.7+torch260cu124 \
  -f https://shi-labs.com/natten/wheels/ >>$LOG 2>&1 || die "natten wheel install failed"
python -c "import natten, torch; from natten.utils.checks import log_or_raise_error; \
  print('natten', natten.__version__)" >>$LOG 2>&1 || die "natten import failed"

step "CUDA extensions (Eigen submodule must be populated or o_voxel fails)"
mkdir -p /tmp/ext && cd /tmp/ext
[ -d CuMesh ]   || git clone -q --recursive https://github.com/JeffreyXiang/CuMesh.git CuMesh >>$LOG 2>&1
[ -d FlexGEMM ] || git clone -q --recursive https://github.com/JeffreyXiang/FlexGEMM.git FlexGEMM >>$LOG 2>&1
rm -rf /tmp/ext/o-voxel && cp -r $W/repos/TRELLIS.2/o-voxel /tmp/ext/o-voxel
if [ -z "$(ls -A /tmp/ext/o-voxel/third_party/eigen 2>/dev/null)" ]; then
  git clone -q --depth 1 -b 3.4.0 https://gitlab.com/libeigen/eigen.git /tmp/eigen >>$LOG 2>&1
  mkdir -p /tmp/ext/o-voxel/third_party/eigen && cp -r /tmp/eigen/* /tmp/ext/o-voxel/third_party/eigen/
fi
[ -d /tmp/extensions/nvdiffrast ] || git clone -q -b v0.4.0 https://github.com/NVlabs/nvdiffrast.git /tmp/extensions/nvdiffrast >>$LOG 2>&1
for t in /tmp/ext/CuMesh /tmp/ext/o-voxel /tmp/ext/FlexGEMM /tmp/extensions/nvdiffrast; do
  step "build $(basename $t)"
  pip install --no-build-isolation "$t" >>$LOG 2>&1 || die "build failed: $t"
done
cd /root
python - <<'PY' 2>&1 | tee -a $LOG
import importlib
for m in ["cumesh","o_voxel","flex_gemm","natten","nvdiffrast.torch","diffusers","trimesh"]:
    importlib.import_module(m); print("  ok", m)
PY
[ $? -eq 0 ] || die "import verification failed"

# The NAF upsampler is pulled from torch.hub at *pipeline construction* time,
# so anything it needs goes missing only once inference has started and the
# GPU is billing. Load it here instead: in the install phase a missing
# dependency costs nothing. (einops was exactly this failure.)
step "preloading torch.hub NAF upsampler (catches its deps before inference)"
python - <<NAFPY 2>&1 | tee -a $LOG
import torch
m = torch.hub.load("valeoai/NAF", "naf", pretrained=True, trust_repo=True)
print("  ok NAF loaded:", type(m).__name__)
NAFPY
[ ${PIPESTATUS[0]:-1} -eq 0 ] || die "NAF preload failed - fix before spending inference time"

step "waiting for checkpoint download"
wait $DL
du -sh $W/models/pixal3d | tee -a $LOG
# Construct the whole pipeline once WITH network. DinoV3 and NAF are fetched
# during construction, so this is what actually fills the caches -- and it runs
# every preflight check while a miss is still cheap to fix.
step "warming caches: full pipeline construction + preflight (network allowed)"
RV_PREFLIGHT_OFFLINE=0 python /workspace/tools/preflight.py 2>&1 | tee -a $LOG
[ ${PIPESTATUS[0]:-1} -eq 0 ] || die "cache-warming preflight failed"

# stamped only now: a failed warm must not look like a completed install
date -u +%FT%TZ > $W/logs/install_done
step "INSTALL PHASE COMPLETE"
exit 0
fi   # end install phase

# ------------------------------------------------------------------ generation
[ -f $W/logs/install_done ] || die "install phase never completed"

step "ASSERT image_attn_mode == 'proj' on every flow model (shell gate)"
python - <<GATEPY 2>&1 | tee -a $LOG
import json, glob, os, sys
bad=[]; checked=0
for f in sorted(glob.glob("/workspace/models/pixal3d/ckpts/*.json")):
    d=json.load(open(f)); args=d.get("args",{}); name=d.get("name","")
    if "flow" not in os.path.basename(f).lower() and "Flow" not in name: continue
    checked+=1; mode=args.get("image_attn_mode"); ok=(mode=="proj")
    print(f"  {'OK ' if ok else 'BAD'} {os.path.basename(f):52s} {name:26s} {mode!r}")
    if not ok: bad.append(os.path.basename(f))
if checked!=4: print(f"  !! expected 4 flow models, found {checked}"); sys.exit(2)
if bad: print("  ASSERTION FAILED:", bad); sys.exit(3)
print("  ASSERTION PASSED on 4 flow models")
GATEPY
[ ${PIPESTATUS[0]:-1} -eq 0 ] || die "image_attn_mode assertion failed - refusing to spend GPU"

step "preflight (offline) + ONE generation attempt, seed 1, 1024"
cd $W/repos/Pixal3D
python /workspace/tools/generate.py 2>&1 | tee -a $LOG
GEN_RC=${PIPESTATUS[0]:-1}

step "packaging outputs"
cd $W/out 2>/dev/null && sha256sum * > SHA256SUMS 2>/dev/null
ls -la $W/out/ | tee -a $LOG
if [ "$GEN_RC" -ne 0 ]; then die "generation failed (rc=$GEN_RC)"; fi
step "RUN3 DONE"; date -u +%FT%TZ > $W/logs/run3_done
