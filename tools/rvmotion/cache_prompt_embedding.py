"""Cache the bf16 prompt embedding from one clean text-encoder load.

Kimodo and ARDY both need LLM2Vec/Llama-3-8B in bf16 (~16 GB) purely to turn a
prompt into a fixed-size vector. This workstation has 15 GB RAM and 11.6 GB VRAM
and cannot host it. The motion model itself is small and runs on the 3060 easily.

So: load the encoder ONCE somewhere it fits, save the embedding, and reuse it.
The prompt text is part of the cache key, so a changed prompt cannot silently
reuse a stale vector.

  # where the encoder fits (e.g. the rented >=24 GB box):
  python3 cache_prompt_embedding.py save --src <checkout> --prompt "..." --out cache/
  # afterwards, locally:
  python3 cache_prompt_embedding.py load --cache cache/ --prompt "..."
"""
import argparse
import hashlib
import json
import os
import sys


def key_for(prompt, encoder):
    h = hashlib.sha256(("%s\x00%s" % (encoder, prompt)).encode()).hexdigest()[:32]
    return h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["save", "load"])
    ap.add_argument("--src"); ap.add_argument("--prompt", required=True)
    ap.add_argument("--out"); ap.add_argument("--cache")
    ap.add_argument("--encoder", default="llm2vec-llama3-8b-mntp-supervised")
    a = ap.parse_args()
    k = key_for(a.prompt, a.encoder)

    if a.mode == "save":
        import numpy as np, torch
        sys.path.insert(0, a.src)
        from kimodo.model.load_model import _build_local_text_encoder_conf
        from hydra.utils import instantiate
        enc = instantiate(_build_local_text_encoder_conf())
        with torch.no_grad():
            emb = enc([a.prompt])
        emb = emb.detach().to(torch.float32).cpu().numpy()
        os.makedirs(a.out, exist_ok=True)
        np.save(os.path.join(a.out, k + ".npy"), emb)
        json.dump({"prompt": a.prompt, "encoder": a.encoder, "key": k,
                   "shape": list(emb.shape), "dtype_generated": "bfloat16",
                   "note": "stored as float32; cast back to bf16 at use"},
                  open(os.path.join(a.out, k + ".json"), "w"), indent=2)
        print("cached %s -> %s.npy %s" % (a.encoder, k, emb.shape))
    else:
        import numpy as np
        p = os.path.join(a.cache, k + ".npy")
        if not os.path.exists(p):
            raise SystemExit("no cached embedding for this exact prompt+encoder (%s). "
                             "Caches are keyed on the prompt text, so an edited "
                             "prompt must be re-encoded rather than silently reused." % k)
        print("hit:", p, np.load(p).shape)


if __name__ == "__main__":
    main()
