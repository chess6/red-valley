# Repository hygiene

## Why this exists

This repository once tracked **346 MB of regenerable binaries against 26 MB of
source** — working Blender checkpoints, intermediate GLB/FBX exports, and 118
iterative diagnostic renders. Undoing it needed a full history rewrite
(`eddbd494`, 229 MiB → 15.6 MiB). The tooling here exists so that cannot recur
silently.

## Enable the hooks (required once per clone)

`core.hooksPath` is local config and does **not** travel with a clone:

```bash
git config core.hooksPath .githooks
```

## `.githooks/pre-commit` — blocks re-entry

Refuses to commit `*.png *.jpg *.mp4 *.webm *.mov *.log *.out *.blend
*.blend1 *.fbx` and any `.glb` under `art/`.

Always allowed:
- anything in `tools/hygiene_allowlist.txt` (explicitly approved production assets)
- `assets/**` — shipping game assets, script-generated and small
- `*.npz` — paid ARDY motion clips, which cost cloud compute and cannot be
  regenerated locally

Deliberate override: `git commit --no-verify`. To promote something to a
production asset, add its exact path to `tools/hygiene_allowlist.txt`.

## `.githooks/post-commit` — reports every 10 commits

Counts commits since the rewrite base `eddbd494`. On each multiple of 10 it:

1. runs `tools/repo_hygiene.py` (report only), and
2. reminds you the rollback bundle can be removed.

It never deletes, never blocks, and never acts without you.

## `tools/repo_hygiene.py` — report only

Audits ignored/untracked generated files under `art/`, reporting path, size and
which script regenerates each one. **Protected and never proposed for removal:**
everything tracked by Git, everything recorded in
`~/RedValleyAssets/MANIFEST.sha256`, the `.npz` clips, and the allowlist.

Proposals move files to **trash**, never `rm`, and only after you read and run
the generated script yourself:

```bash
python3 tools/repo_hygiene.py                      # report
python3 tools/repo_hygiene.py --trash-script       # writes .hygiene_trash.sh
less .hygiene_trash.sh && bash .hygiene_trash.sh   # only if you agree
```

## Storage split

| location | role | lifetime |
|---|---|---|
| the Git repo | source, docs, manifests, checksums, approved production assets | permanent |
| `~/RedValleyAssets/` | **permanent source storage** — Rodin master, character lineage, working Rigify sources, Mixamo evidence, paid clips | permanent |
| `~/RedValleyAssets/git_backup/` | **temporary** pre-rewrite rollback bundle | until 10 clean commits past `eddbd494` |

Verify the private store with `sha256sum -c MANIFEST.sha256` from inside it.
