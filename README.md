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
| 1 | Generic navigation to a target | 🔨 in progress | ⏳ pending |
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
