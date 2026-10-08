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
| 1 | Generic navigation to a target | ✅ VERIFIED | ⏳ UNVERIFIED — NavTest procedure below |
| 2 | Wall-pinch geometry (SEARCH/SETUP) | — | — |
| 3 | Wall geometry physically believable | — | — |
| 4 | Car reaches the pinch setup point | — | — |
| 5 | Pinch stabilization | — | — |
| 6 | First pinch EXECUTE attempt | — | — |
| 7 | Pinch VERIFY | — | — |
| 8 | RECOVER / retry | — | — |
| 9 | Reliable Kuxir wall pinch | — | — |

Legend: ✅ verified · ⏳ pending · — not started. Later: ground (10), ceiling
(11), advanced/Aztral-style (12).

## Layout

```
PinchBot/
├── src/
│   ├── bot.py            # the bot (Stage 0 foundation; BaseAgent subclass)
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

## Stage 0 — what the bot does

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
2. Open **RLBotGUI** → add bot from file → select `src/pinch_bot.cfg`
   (install requirements if prompted). PinchBot appears on the blue team.
3. Start an **Exhibition** match (or Free Play) on any map.
4. Watch PinchBot the moment the kickoff countdown ends.

**Expected:** PinchBot sits still for ~1 second, then drives **straight forward**
for ~1.5 seconds, then releases and coasts to a stop. It does **not** turn,
reverse, or spam inputs. The console shows the `IDLE → THROTTLE → STOP` states.

If that is what you see, Stage 0 is **physically VERIFIED**. If it drives the
wrong way, never moves, or jitters, report exactly what happened (and the
telemetry lines) — that is a real bug to diagnose, not to tune around.

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
