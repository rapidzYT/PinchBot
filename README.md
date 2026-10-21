# PinchBot

An RLBot (v4 API, RLBot `1.68.0`) Rocket League bot being built toward reliable
**Kuxir-style wall pinches**, and later ground / ceiling / advanced pinches.

The project is built **incrementally and evidence-first**. Each layer is proven
in software *and* physically in Rocket League before the next layer is stacked
on top. Nothing is called "done" on the strength of code or unit tests alone;
gameplay features require a physical RLBot GUI test.

## Status (checkpoint ledger)

| # | Milestone | Software | Physical (in-game) |
|---|-----------|----------|--------------------|
| 0 | RLBot foundation (loads, controls the car) | ✅ VERIFIED | ✅ VERIFIED (2026-10-08) — **foundation frozen** |
| 1 | Generic navigation to a target | ✅ VERIFIED | ✅ VERIFIED (2026-10-08) — **navigation frozen** |
| 2 | Wall-pinch geometry (SEARCH/SETUP) | ✅ VERIFIED | ✅ VERIFIED (2026-10-21) |
| 3 | Wall geometry physically believable | ✅ VERIFIED | ✅ VERIFIED (2026-10-21) |
| 4 | Car reaches the pinch setup point (`StabilizeTest`) | ✅ VERIFIED (software) | — |
| 5 | Pinch stabilization (`SEARCH → STABILIZE → HOLD`, no contact) | ✅ VERIFIED (software) | — |
| 6 | First pinch EXECUTE attempt (`ExecuteTest`) | ✅ VERIFIED (software) | — |
| 7 | Pinch VERIFY and conservative result classification | ✅ VERIFIED (software) | — |
| 7a | Integrated `PinchBot` setup-only controller | ✅ VERIFIED (software) | — |
| 8 | RECOVER / retry | — | — |
| 9 | Reliable Kuxir wall pinch | — | — |

Legend: ✅ verified · ⏳ pending · — not started. Later: ground (10), ceiling
(11), advanced/Aztral-style (12).

## Layout

```
PinchBot/
├── src/
│   ├── bot.py            # frozen Stage 0 foundation regression bot
│   ├── pinchbot.py       # integrated PinchBot; setup-only until reliable
│   ├── navtest.py        # Stage 1 generic navigation test bot
│   ├── geomtest.py       # Stage 2 render-only geometry inspection bot
│   ├── stabilize_test.py # Stage 4/5 setup stabilization bot; no contact
│   ├── stabilize_test.cfg
│   ├── execute_test.py    # Stage 6/7 first contact + verification bot
│   ├── execute_test.cfg
│   ├── pinch_bot.cfg     # RLBot bot config (add THIS in RLBotGUI)
│   └── appearance.cfg    # loadout
├── tests/                # software validation (pytest)
│   ├── fake_packet.py    # builds a real GameTickPacket struct for tests
│   └── test_stage0_foundation.py
├── rlbot.cfg             # top-level match config (CLI runner / reference)
├── requirements.txt      # rlbot==1.68.0
└── conftest.py           # puts src/ on sys.path for tests, as RLBot does
```

## Environment

* Windows 11, Rocket League (Steam), RLBot GUI, RLBot `1.68.0`, Python `3.11.x`.
* API style is **RLBot v4**: `BaseAgent`, `SimpleControllerState`,
  `GameTickPacket`, `initialize_agent()`, `get_output(packet)`.

## Running the tests (software validation)

From the RLBot Python environment (the one with `rlbot` installed):

```
python -m pytest
```

## Stage 0 — frozen foundation (`bot.py`)

A deliberately tiny, deterministic proof of the full pipeline. On the first tick
the round is live, it anchors a clock to real game time and runs, in a straight
line (`steer = 0` throughout):

1. **IDLE** (`throttle 0`) for 1.0 s — sit still so the start state is visible.
2. **THROTTLE** (`throttle 1`) for 1.5 s — accelerate forward.
3. **STOP** (`throttle 0`) — release and coast to a stop, then hold.

Concise telemetry prints about every 30 ticks (`state`, `tick`, `car_pos`,
`car_vel`, `ball_pos`, `throttle`, `steer`, ...).

### Physical RLBot GUI test for Stage 0

1. Copy/clone this project to `C:\Users\omars\source\repos\PinchBot`.
2. The Stage 0 implementation remains in `src/bot.py` for regression tests.
   The normal `src/pinch_bot.cfg` now loads the integrated setup controller below.
3. Start an **Exhibition** match (or Free Play) on any map.
4. Watch PinchBot the moment the kickoff countdown ends.

**Expected for a direct Stage 0 config:** the foundation sits still for ~1 second, then drives **straight forward**
for ~1.5 seconds, then releases and coasts to a stop. It does **not** turn,
reverse, or spam inputs. The console shows the `IDLE → THROTTLE → STOP` states.

If that is what you see, Stage 0 is **physically VERIFIED**. If it drives the
wrong way, never moves, or jitters, report exactly what happened (and the
telemetry lines) — that is a real bug to diagnose, not to tune around.

## Current main bot — integrated setup-only `PinchBot`

`src/pinch_bot.cfg` now loads `src/pinchbot.py`, which combines the live
wall-pinch geometry/navigation stages into the bot named **PinchBot**. It can
choose a side wall, drive behind a midfield ball, push the ball toward that
wall, then switch to bounded predicted pre-positioning and stabilize at the
pinch setup point. Boost is used only on long aligned travel. The Kuxir pinch
execution remains disabled until this setup-making behavior is physically
reliable.

### Physical test for the current main bot

1. In RLBotGUI, add or reload `src/pinch_bot.cfg` and start Free Play.
2. Press **Page Up** to enable rendering.
3. Start with the ball near midfield and keep other cars out of the way.

**Expected:** PinchBot shows `CREATE_SETUP`, approaches from the interior side,
and pushes the ball toward its selected side wall. Once the ball is near the
wall, it transitions through `SETUP`/`STABILIZE` and holds the lime setup point.
Telemetry is prefixed `[PinchBot]`; there should be no `EXECUTE` state. This is
the physical gate before the Kuxir pinch is merged into the main bot.

## Stage 1 — generic navigation (NavTest)

A separate bot, `NavTest`, exercises the reusable navigation controller
(`src/navigation.py`). It drives to a **target point** and stops cleanly, with
these guarantees (enforced by `tests/test_navigation.py`):

* **Steering** uses the proven RLBot convention `clamp(atan2(local.y, local.x)·5, −1, 1)`.
* **No blind reverse** — `throttle < 0` is only ever braking against current
  forward motion; a target behind is reached by *turning around* under forward
  throttle, never by driving backwards.
* **Clean arrival** — desired speed is derived from the remaining stopping
  distance (`v = √(2·a·d)`), so the car decelerates to 0 at the target and holds,
  without circling or jittering.

For the physical test, `NavTest`'s target is the **ball** projected to the
ground, with `arrival_radius ≈ 202 uu`, so it stops *just short* of the ball
(no intentional contact). It renders a lime line to the target, a cyan marker,
and a status string.

### Physical RLBot GUI test for Stage 1

1. Pull the latest `claude/sweet-mendel-b2c8sv` branch.
2. In **RLBotGUI**, add bot from file → select `src/navtest.cfg` (name shows as
   **NavTest**). Run it in **Free Play** (easiest: you can drag the ball around).
3. Watch once the round is live.

**Expected:** NavTest turns to face the ball, drives to it, slows down, and
**stops just short of it** (a small gap, no big shove). Then **move the ball**
somewhere else — it should turn toward the new spot and repeat, approaching
cleanly from any angle. It should **not** circle the ball, drive away, or sit
there spamming reverse. The overlay/console show `DRIVE → BRAKE → ARRIVED`,
`heading_error` shrinking toward 0 as it lines up, and `dist` settling near 202.

If that is what you see, Stage 1 is **physically VERIFIED**. If it orbits,
reverses toward a ball behind it, overshoots and never settles, or drives to the
wrong place, report the telemetry — that is a real bug to diagnose.

## Stage 2 — wall-pinch geometry (GeomTest, render-only)

`src/wall_pinch_geometry.py` computes a Kuxir side-wall pinch **setup** from the
live ball state: selected wall, inward normal, along-wall tangent (signed to the
pinch direction), contact point, the car's approach/setup point, approach
direction, and the expected exit direction — with a full validation layer that
**rejects** bad setups with an explicit reason (`ball_not_near_wall`,
`ball_too_high`, `ball_near_corner`, `target_out_of_bounds`, …) and never emits a
nonsense target. The relationship is **CAR → BALL → WALL** (car interior, wall
far side). Constants come from `src/field.py` (verified field values).

`GeomTest` (`src/geomtest.cfg`) is a **render-only inspection bot — it NEVER moves
and never touches the ball.** It draws the computed setup and a status line.

### Physical inspection test for Stage 2 (zero ball contact)

1. Pull the branch. In **RLBotGUI**, add bot from file → `src/geomtest.cfg`
   (shows as **GeomTest**). Run in **Free Play**.
2. The car will **sit still**. Drag the **ball up against a side wall**.
3. Look at the rendered overlay:
   - **cyan** cube = ball, **white** line = the selected wall segment,
   - **red** cube = contact point (should sit on the ball's *interior-facing* side),
   - **lime** cube + line = the car's setup point and the approach vector
     (should start further toward midfield and point diagonally into the ball
     toward the wall),
   - **yellow** line = expected exit direction (along the wall),
   - status text shows `wall=RIGHT/LEFT`, `VIABLE`, and the gap/distance.

**What to check:** the right wall is picked when the ball is on the +x side (left
on −x); the contact/approach points and vectors sit sensibly (car→ball→wall), and
the whole picture tracks the ball as you drag it. Move the ball to **midfield** →
it should show `REJECT:ball_not_near_wall`; drag it into a **corner** →
`REJECT:ball_near_corner`. The car must never move.

If the drawn geometry matches the real field as you move the ball, Stage 2 is
**physically verified** and we proceed to STABILIZE (driving to the setup point).

## Stage 4/5 — setup stabilization (StabilizeTest, zero ball contact)

`StabilizeTest` (`src/stabilize_test.cfg`) is the first live bot that combines
the wall-pinch geometry with navigation. For each tick it recomputes the setup
from the ball's current position and velocity, then drives to the lime
`approach_point` and holds there. It never targets the contact point, never
jumps or boosts, and has no `EXECUTE` path.

The state labels are observable in the overlay and telemetry:

* `WAIT` — round is not active; hold neutral.
* `SEARCH` — no viable wall setup or no safe early approach; hold neutral and
  report the geometry reason.
* `SETUP` — the ball is within the early-warning band and moving toward the
  wall, so start pre-positioning at the safe approach point before the strict
  near-wall gate becomes viable. This is still zero-contact setup motion.
* `STABILIZE` — navigate to the current viable setup point while reporting distance,
  heading error, velocity toward target, and ball-wall gap.
* `HOLD` — the navigation controller reports arrival inside the setup radius;
  keep neutral controls.
* `RECOVER` — repeated distance/heading regression or a timeout; hold neutral
  briefly, then regenerate the setup. A timer cannot advance to execution.

### Physical RLBot GUI test for Stage 4/5

1. In RLBotGUI, add bot from file → select `src/stabilize_test.cfg` (name shows
   as **StabilizeTest**). Run it in Free Play and press **Page Up** to enable
   rendering.
2. Place the ball flush against the middle of a side wall, away from the
   rounded corner. A ball around the observed low wall height is the intended
   setup; do not start with the ball high on the wall.
3. Watch the lime setup marker and the cyan car-to-target line.

**Expected:** the car turns and drives to the lime approach marker, slows down,
and holds there without touching the ball. The marker remains on the interior
side of the ball, with the relationship **CAR → BALL → WALL**. Telemetry should
show `STABILIZE` with distance trending down, then `HOLD` with distance within
about 140 uu and neutral controls. Move the ball along the wall: the bot should
regenerate and re-stabilize. Move it to midfield or into a corner: the bot
should stop and show `SEARCH` with `ball_not_near_wall` or `ball_near_corner`.

This checkpoint is **not physically verified** until those observations are
confirmed in Rocket League. Paste several `[StabilizeTest]` telemetry lines,
including `wall_vel` during `SETUP`, the transition to `HOLD`, and any
rejection/recovery behavior, before marking it physically verified.

## Stage 6/7 — first contact attempt (ExecuteTest)

`ExecuteTest` (`src/execute_test.cfg`) is the first bot allowed to make
intentional ball contact. It retains the strict wall geometry and only enters
`EXECUTE` after the car is grounded, within the setup gate, and aligned with
the diagonal approach direction. It then sends one short bounded throttle pulse
toward the predicted car contact-center line, stops, and observes the ball.

The result is intentionally conservative: `MISS`, `SOFT_CONTACT`,
`NORMAL_CONTACT`, or `POSSIBLE_PINCH`. `POSSIBLE_PINCH` means the ball gained
substantial speed along the expected wall tangent; it is not yet proof that the
ball was compressed between car and wall. There is no automatic
`PINCH_CONFIRMED` claim at this stage.

### Physical RLBot GUI test for the first contact

1. Add `src/execute_test.cfg` in RLBotGUI and run it in Free Play. Press
   **Page Up** to enable rendering.
2. Place the ball low on a side wall, well away from both corners. Use a fresh
   round and keep other cars out of the way.
3. Watch for `STABILIZE` followed by `EXECUTE`. The orange marker is the
   predicted car contact-center line; the attempt may move the ball.

**Expected:** if the car reaches the gate while the ball is still viable, it
drives diagonally into the ball once, then enters `VERIFY` and holds neutral
controls. Paste the `[ExecuteTest]` lines containing `EXECUTE`, `VERIFY`, and
the final `result`, plus the observed ball motion. If the ball leaves the wall
before the gate, the bot should remain safe and report `SEARCH`; that is a
missed opportunity, not a confirmed pinch.

This milestone is **not physically verified** until a human observes the first
contact and reports the actual result. Do not tune the thresholds from a single
lucky outcome; record the telemetry first.
