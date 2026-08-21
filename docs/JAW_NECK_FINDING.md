# Jaw/neck blend band — investigated, NOT established as a defect

**Outcome: the "80% strain" blocker is not confirmed, and the metric that produced
it is unreliable. No production mesh weights were changed.**

## What was found

The band is 984 vertices spanning 0.099 m. It is **not** a two-bone head/neck
blend: `DEF-spine.005` carries **45% of its weight across 977 of the 984
vertices**, with `DEF-spine.003` and both shoulders contributing further. Any gate
that reasons about it as "head versus neck" is describing something that does not
exist.

## Why the number cannot be trusted

The same band, same mesh, measured three ways:

| method | result |
|---|---|
| rotate the `head` bone alone by 30° | **190%** |
| distribute 30° across neck + head, 50/50 | **24%** |
| `validate.py` face gate on a retargeted clip | **80%**, then **946%** on a rebuild |

An order of magnitude of spread depending on how the head is posed. The 946%
figure is not physically plausible, which condemns the metric rather than the
mesh. The gate measures edge strain relative to the clip's first frame, so it
inherits whatever that frame happens to be.

**The one controlled measurement — a realistic 30° turn shared across the chain —
gives 24%, which passes the 25% gate.**

## What was tried and rejected

Weight smoothing over the band (12 iterations, both groups) reduced strain by 4%
and *narrowed* the band from 984 to 907 vertices — the opposite of the intent. Not
adopted; the production mesh is unchanged.

A `--neck-share` option was added to the retargeter to move part of the head's
local rotation onto the neck while restoring the head's absolute world orientation,
so gaze is untouched. It shifted the split from 58% to 47% head-heavy as designed,
but the face gate then reported a *worse* number. **Default is 0.0 (disabled).**
The mechanism is sound and the option is kept, but it is not enabled on the
strength of a metric that disagrees with itself.

## What is solid

The **face core is rigid at 0.017–0.021%** in every measurement, by every method.
The face itself does not deform. That was the original concern and it is answered.

## Recommendation

Do not paint weights on the production mesh for this. Rebuild the face gate first
so it measures a *defined* head pose rather than whatever frame 1 contains, and
account for the real four-bone weighting. Only then is it worth asking whether a
defect exists.
