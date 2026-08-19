# Red Valley — gameplay vision

The authoritative scope document. Sections are split into **1. Implemented
now** (proven by code and tests), **2. Confirmed future design** (stated in
README/CLAUDE.md/STATUS.md as intent, not yet built), and **3. Unconfirmed /
open questions** (assumptions that must not be built on until answered).

Nothing here is inferred from asset filenames. Where an asset exists but the
behaviour does not, it is called out explicitly.

---

## Premise

A 3D farming game about **thinking like a farmer** — reading land and weather
and making judgment calls under real time pressure — rather than performing
farming-themed chores. The player learns a specific piece of ground: which
corner dries first, which field drowns after a storm, when the forecaster is
worth believing.

The design thesis, protected in `CLAUDE.md`: one causal chain,
**weather → soil → crop → player-time**, with **no scripted events**. Every
dilemma must emerge from those four systems' numbers.

---

## 1. Implemented now

### Minute-to-minute loop
Walk the farm → read plots (visually and by inspecting) → choose which of
several competing jobs the remaining daylight can afford → act → watch the
consequence land overnight.

Time is the core resource. 1 real second = **1.15 game minutes** while
playing, and each field action additionally consumes a fixed block of game
minutes:

| Action | Minutes | Notes |
|---|---|---|
| Inspect | 2 | qualitative report, always allowed |
| Water | 8 | |
| Uncover | 8 | |
| Compost / Manure / Mulch | 10 each | |
| Plant / Harvest / Clear dead | 12 each | |
| Row cover | 18 | the expensive one |

Day boundaries: wake **06:00**, forced collapse at **02:00** (you black out
and wake at 06:00). Night (21:00–05:30) blocks water, seeds, compost, manure
and mulch. **Covering is deliberately allowed after dark** — scrambling
against frost is the one night job. Hand actions (harvest, clear, uncover,
inspect) stay available.

### Player capabilities (exhaustive, from `src/player/player.gd`)
- **Locomotion**: walk 4.3 m/s, run 7.0 m/s (Shift). Third-person orbit camera
  on a spring arm. The character model rotates to face its direction of
  travel. **There is no jump** — no jump action exists in the input map.
- **Targeting**: raycast from the camera, 9 m range, collision layer 2.
- **Hotbar 1–7**: Hand, Watering can, Seeds, Compost, Manure, Mulch, Row
  cover. Pressing 3 again cycles crop (tomato → cabbage → potato → wheat).
  Tool switching is instantaneous and has no time cost.
- **Use tool (LMB)** on the targeted plot, dispatching by tool and plot state.
- **Hand** is contextual: fold away a cover → clear a dead plant → harvest a
  ripe crop → salvage an unripe one (two presses within 3 s to confirm, own
  plots only) → otherwise inspect.
- **Inspect (F)**, **Interact (E)**, **Wait one hour (T)**.

### Interactables (exhaustive, from `src/world/world.gd`)
Only three exist:
1. **Farmhouse door** → "Sleep until morning"
2. **Supply crate** → "Browse supplies" — opens a **shop UI panel**
3. **Sarah** → dialogue panel

> **The crate is scenery plus a UI trigger.** The player does not pick it up,
> carry it, or open a lid. `well.glb`, `bin.glb`, `shed.glb` and the windmill
> are **non-interactive props**; the well is not a water source and watering
> requires no refill.

### Farming systems
- **Soils**: sandy, loam, clay — genuinely different drainage/retention. Same
  rain, three different fields.
- **Crops**: tomato, cabbage, potato, wheat, sharing one response model
  (moisture band, drought rate, waterlog tolerance, frost threshold, heat
  threshold, fertility hunger). All drama emerges from those numbers.
- **Amendments**: compost (gentle), manure (strong, scorches seedlings), mulch
  (retains water), row cover (~5 °C of warmth, sheds rain, costs light).
  Nothing is a strict upgrade of anything else.
- **Information is observational** — "the leaves are slightly wilted", never
  `moisture=0.43`. Raw numbers live behind F3 only.

### Weather
Markov chain over six patterns (clear, hot & dry, overcast, rain, heavy rain,
cold snap) with a **deliberately imperfect forecast**. A protected invariant:
no announced probability may deterministically predict the outcome, guarded
over a 3000-day sample in both directions.

### Economy
Thin by design at this stage: harvest **auto-sells** for coins at the moment
of harvesting; the shop sells seeds and amendments at static prices; start
with 25 coins. **There is no hauling, no storage, no market travel.**

### Sarah and reciprocity
Sarah farms her own land with the same simulation, in three states —
**IDLE / WALK / WORK**. She routes between the two farms through a gate in the
boundary fence, waters her driest beds by day, covers her frost-tender crops
in the evening, and harvests what is ripe.

Helping her (watering, covering, bringing in her harvest) earns reciprocity,
capped at 5/day. Asking her for help costs reciprocity (cover 3, water 2),
is limited to **once per day**, and she brings only **2 spare fleeces** (or
waters 4 beds). Both limits exist so that her help cannot dissolve the frost
scarcity the game is built around.

### The signature situation
Unscripted but reliably produced: tomatoes and cabbage in the ground, a frost
warning at 51%, four hours of daylight left, covers enough for half the field.
Cover the tomatoes and gamble the cabbage? Salvage early at half yield? Spend
a favour on Sarah? The morning after answers you.

### Progression
There is **no XP, no tech tree, no unlocks**. The progression system is the
player's own understanding of the land. A session is one sitting — **no
save/load** (a deliberate prototype cut).

---

## 2. Confirmed future design

Stated as intent in the repo, not yet implemented.

- **The day must become genuinely finite.** `STATUS.md` records that it
  currently is not: watering *and* covering every plot costs 58% of the usable
  day, so a player can do everything with hours to spare. Named candidates:
  shorten the workable window, raise action costs, or shrink the farm. This is
  flagged as a balance decision, deliberately not taken unilaterally.
  **It changes the cost of actions, not the set of actions.**
- **A field journal** — README's "highest-value next improvement". Lets the
  player pin observations to plots and auto-logs nightly outcomes plus
  forecast-vs-reality history, turning inference into a first-class mechanic.
- **Save/load** — acknowledged as cut for the prototype, not rejected.
- **Real navmesh pathfinding for Sarah** — current waypoint-through-the-gate
  routing clips building corners.
- **A rigged, animated player character** replacing the rigless blockpeople;
  "animation" today is procedural bobbing.
- **Deeper economy** — current one is explicitly described as "thin".
- **Better dramatisation of heat and fertility**, which currently register
  only through inspection text.
- **Audio** — absent.

### Character presentation (confirmed for the animation work)
- **Tools are visibly held.** Visible props are part of the intended
  presentation; tools must not be architected as permanently abstract. P0 adds
  a hand socket and a real watering can. Row-cover work manipulates the
  existing plot cover prop. Seeds and amendments temporarily share one
  hand-scatter motion.
- **Sarah shares the player's skeleton**, with per-task work motions rather
  than one generic bent-over loop.
- **ARDY is NVIDIA ARDY** — a text- and constraint-driven human *motion*
  generator (NPZ joint transforms on NVIDIA Core/G1 skeletons). It supplies
  motion only, never rigs or meshes, and must not dictate the game's
  production skeleton. Its code is Apache-2.0 and the Core checkpoint is
  stated as commercial-ready.
- **Interaction alignment is a contract, not an assumption** — actors snap and
  turn to a standardized plot anchor before plot-directed actions. See
  `docs/ANIMATION_REQUIREMENTS.md`.

---

## 3. Unconfirmed / open questions

Do not build on any of these until answered.

- **OPEN — does the player ever carry anything?** Harvest auto-sells and there
  is no carried-item state. Deferred: build assuming no carrying, revisit if
  hauling is added.
- **UNCONFIRMED — will harvest ever route through hauling/storage** (basket,
  bin, cart) rather than auto-selling.
- **UNCONFIRMED — is dialogue ever embodied?** Talking opens a UI panel; there
  is no conversation framing, gesture, or camera move.
- **UNCONFIRMED — is sleeping ever shown?** It is currently an instant clock
  advance behind a confirm dialog.
- **UNCONFIRMED — will the farm gain terrain relief?** Ground is effectively
  flat today, which determines whether foot IK is required.
