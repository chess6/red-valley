"""Pre-inference preflight, run in the same process that will generate.

Everything here answers one question: will the generation attempt fail for a
reason we could have found for free? Run 2 died 137s into inference on a
missing `einops` inside a torch.hub repo -- a failure that cost GPU time only
because nothing had exercised that path first.

Same process as generation on purpose: instantiating the pipeline costs
minutes and ~23GB of weight loading, so doing it once and then generating with
that same object is the difference between a preflight and a second rental.

Any check that fails raises. There is no partial pass.
"""
import inspect
import json
import os
import socket
import subprocess
import sys

import torch

MODEL = "/workspace/models/pixal3d"
REPO = "/workspace/repos/Pixal3D"
report = {}


def head(t):
    print(f"\n=== PREFLIGHT: {t} ===", flush=True)


def fail(msg):
    raise SystemExit(f"PREFLIGHT FAILED: {msg}")


# ---------------------------------------------------------------- 1. pip check
head("pip check")
p = subprocess.run([sys.executable, "-m", "pip", "check"],
                   capture_output=True, text=True)
print(p.stdout.strip() or "(no output)")
report["pip_check_rc"] = p.returncode
report["pip_check"] = (p.stdout + p.stderr).strip()
# torchaudio pins torch==2.5.1 while we deliberately run 2.6.0; that pairing is
# unused here. Anything else unmet is a real problem.
bad = [l for l in report["pip_check"].splitlines()
       if l.strip() and "torchaudio" not in l]
if bad:
    fail("unmet dependencies: " + "; ".join(bad))
print("OK: no unmet dependencies (torchaudio's torch pin is unused and ignored)")

# ------------------------------------------------- 2. NAF: instantiate + forward
head("NAF instantiate and push a real tensor through it")
naf = torch.hub.load("valeoai/NAF", "naf", pretrained=True, trust_repo=True)
naf = naf.cuda().eval()
sig = str(inspect.signature(naf.forward))
print("NAF forward signature:", sig)
report["naf_signature"] = sig

# NAF is forward(image, features, output_size, ...): output_size is a
# REQUIRED positional. Feature width depends on the DINO variant feeding it,
# so probe a few rather than assuming one.
H = W = 224
img = torch.randn(1, 3, H, W, device="cuda")
ok = None
errors = {}
for C in (384, 768, 1024, 256, 512):
    feat = torch.randn(1, C, 16, 16, device="cuda")
    try:
        with torch.no_grad():
            out = naf(img, feat, output_size=(H, W))
        shape = tuple(out.shape) if torch.is_tensor(out) else type(out).__name__
        print(f"OK: naf(image[1,3,{H},{W}], features[1,{C},16,16], "
              f"output_size=({H},{W})) -> {shape}")
        ok = {"call": f"naf(image[1,3,{H},{W}], features[1,{C},16,16], "
                      f"output_size=({H},{W}))", "out": str(shape)}
        break
    except Exception as exc:
        errors[f"C={C}"] = f"{type(exc).__name__}: {exc}"[:180]
if not ok:
    for k, v in errors.items():
        print(f"  {k}: {v}")
    fail("NAF would not execute any tensor -- it is exercised during inference")
report["naf_forward"] = ok
del img, feat, naf, out
torch.cuda.empty_cache()

# ------------------------------------- 3. flow models still in projection mode
head("reconfirm image_attn_mode == 'proj' on all four flow models")
import glob
modes = {}
for f in sorted(glob.glob(os.path.join(MODEL, "ckpts", "*.json"))):
    d = json.load(open(f))
    name = d.get("name", "")
    if "flow" not in os.path.basename(f).lower() and "Flow" not in name:
        continue
    modes[os.path.basename(f)] = (name, d.get("args", {}).get("image_attn_mode"))
for f, (name, mode) in modes.items():
    print(f"  {'OK ' if mode == 'proj' else 'BAD'} {f:52s} {name:26s} {mode!r}")
report["flow_models"] = {k: v[1] for k, v in modes.items()}
if len(modes) != 4:
    fail(f"expected 4 flow models, found {len(modes)}")
if any(m != "proj" for _, m in modes.values()):
    fail("a flow model is not in projection mode")
print("OK: all 4 flow models are 'proj'")

# --------------------------------- 4. build pipeline offline + force every part
# Two passes exist for a reason. The install phase runs this with
# RV_PREFLIGHT_OFFLINE=0 to warm every cache (DinoV3 and NAF are fetched while
# the pipeline is *constructed*, not beforehand). The generation phase then
# runs it with the default, offline, so a cache miss is a hard error and
# "inference needs no network" is demonstrated rather than assumed.
OFFLINE = os.environ.get("RV_PREFLIGHT_OFFLINE", "1") == "1"
head(f"instantiate the pipeline and every lazily loaded component "
     f"({'offline' if OFFLINE else 'network allowed, warming caches'})")
if OFFLINE:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    print("HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 -- a cache miss now is a hard error")

sys.path.insert(0, REPO)
import importlib.util

# briaai/RMBG-2.0 is gated AND non-commercial, and Pixal3D constructs it
# unconditionally at pipeline load. Our input is RGBA with a real alpha channel
# so preprocess_image() never calls it -- stub the constructor only, and make
# any actual invocation loud rather than silently pulling a gated model.
rembg = importlib.import_module("pixal3d.pipelines.rembg")


class _StubBiRefNet:
    def __init__(self, *a, **k):
        pass

    def to(self, *a, **k):
        return self

    def cpu(self):
        return self

    def eval(self):
        return self

    def __call__(self, *a, **k):
        raise RuntimeError(
            "background removal was invoked -- the input lacked real alpha. "
            "That would pull the gated non-commercial briaai/RMBG-2.0.")


rembg.BiRefNet = _StubBiRefNet
print("briaai/RMBG-2.0 stubbed (input is RGBA; invocation would raise)")

spec = importlib.util.spec_from_file_location("pixal_inf", os.path.join(REPO, "inference.py"))
inf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inf)

pipeline = inf.init_pipeline(MODEL, low_vram=False)
print("pipeline:", type(pipeline).__name__)

models = getattr(pipeline, "models", {}) or {}
print(f"components: {len(models)}")
inventory = {}
for name, m in sorted(models.items()):
    params = sum(p.numel() for p in m.parameters()) if hasattr(m, "parameters") else 0
    devs = {str(p.device) for p in m.parameters()} if hasattr(m, "parameters") else set()
    inventory[name] = {"class": type(m).__name__, "params": params,
                       "devices": sorted(devs)}
    print(f"  {name:34s} {type(m).__name__:30s} {params/1e6:9.1f}M  {sorted(devs)}")

# anything still deferred behind a _load_* hook gets forced now, not at inference
forced = []
for name, m in sorted(models.items()):
    for attr in dir(m):
        if attr.startswith("_load_") and callable(getattr(m, attr, None)):
            try:
                getattr(m, attr)()
                forced.append(f"{name}.{attr}")
            except Exception as exc:
                fail(f"lazy loader {name}.{attr} failed: {type(exc).__name__}: {exc}")
print("forced lazy loaders:", forced or "(none)")
report["components"] = inventory
report["forced_lazy_loaders"] = forced
if not inventory:
    fail("pipeline exposes no components -- cannot verify anything is loaded")

# ----------------------------------------- 5. record any network use from here
head("network watch armed for generation")
_attempts = []
_real = socket.socket.connect


def _watched(self, addr, *a, **k):
    try:
        host = addr[0] if isinstance(addr, tuple) else str(addr)
        if not str(host).startswith(("127.", "::1", "localhost")):
            _attempts.append(str(addr))
    except Exception:
        pass
    return _real(self, addr, *a, **k)


socket.socket.connect = _watched
report["network_attempts"] = _attempts
print("OK: outbound connections during generation will be recorded")
report["offline"] = OFFLINE
print(f"\n=== PREFLIGHT PASSED ({'offline' if OFFLINE else 'cache-warming'}) ===", flush=True)
