# Deprecated — LLM-authored geometry generators

These scripts generated art geometry procedurally. **Do not reuse or extend
them.** They are kept only as the evidence behind `docs/ASSET_POLICY.md`.

| Script | What it did | Why it failed |
|---|---|---|
| `s2_garments.py` | Grew garments from body topology via coordinate predicates | Ragged edges, "arm wings", swallowed the hands |
| `s4_vest_panels.py` | Parametric 3D surface-grid vest | Cylindrical projection cannot reach the top of a shoulder |
| `s6_vest_cloth.py` | Flat panels + cloth sewing springs | Four sims, all tore the panels |
| `s8_vest_shell.py` | Assembled quad shell + shrinkwrap + cloth relax | Shell was acceptable; the relax passes destroyed it |

The approach that worked is `s9_asset_vest.py`: take a **human-authored**
garment and adapt it using only topological operations (whole-component
deletion, authored edge rings). Kept as the reference pattern.

Still active and permitted: `s1_base.py` (MPFB parameter setup),
`s5_sleeves.py` (edge-ring cut on an authored mesh), `s7_boots.py`
(proportional reshape of an authored boot), `s9_asset_vest.py`.
