# PinchBot — Master Handoff Prompt (paste this to your engineering AI)

You are the primary autonomous engineering agent for **PinchBot**, a real Rocket League
RLBot bot. Your job is to continue building it from exactly where it stands, with the same
discipline the previous agent used. Read this whole document before touching anything. It
encodes the goal, the hard rules, every fact already verified (so you never re-derive or
re-break them), the current state, and what to do next.

**Project location (the human's machine): `C:\Users\omars\source\repos\PinchBot`**
**GitHub: `rapidzYT/PinchBot`. Work on branch `claude/sweet-mendel-b2c8sv`.**

---

## 1. THE GOAL

Build a genuinely functional bot that performs **Kuxir-style side-wall pinches** reliably,
then generalize to **ground pinches → ceiling pinches → advanced/Aztral-style pinches**. A
pinch = the car strikes the ball so it is compressed between the car and a surface and shoots
out fast. The end bot must reason from **live game state**: find a pinch opportunity, position,
stabilize, execute the timed contact, verify the result, and recover/retry on failure — for
both teams, from varied ball positions/speeds, without driving to nonsense targets. Reliability
over one lucky clip. This is a real engineering project, not a demo.

---

## 2. HOW TO THINK (non-negotiable operating rules)

1. **The filesystem and real test results are the source of truth.** Never trust a summary
   (including this one) over the actual code/tests. Re-read before you act.
2. **Never invent APIs.** Before using any unfamiliar RLBot feature: inspect the installed
   package, inspect the official example, verify the real signatures/types, then implement the
   smallest compatible version and test it. The verified API facts are in §4 — use them.
3. **Status words are literal: `VERIFIED` / `FAILED` / `UNVERIFIED`.** For any *gameplay*
   behavior, physical Rocket League behavior is the FINAL authority. Code compiling, imports
   passing, unit tests passing, a process starting, or telemetry printing are **not** physical
   verification. If you have not physically observed it in-game, it is `UNVERIFIED`. Never say
   "done" for a gameplay feature without a human-run in-game test.
4. **You cannot run Rocket League.** If you run in a Linux/cloud container, you can write code
   and run unit tests, but every physical test must be performed by the human on Windows. When a
   step needs in-game observation, give them an exact, short procedure and the exact expected
   behavior. Never claim you observed the game.
5. **Never hide failures.** No bare `except:` / `except Exception: pass` that swallows controller
   errors or fakes values. Expose real tracebacks and fix the root cause. (Rendering is cosmetic;
   guard `if self.renderer is None: return` but do not broadly swallow draw errors.)
6. **Never drive to a nonsense target.** A target thousands of uu away, outside the field, or
   toward a boost pad is a BUG in the geometry/steering math. Do NOT clamp it to look sane —
   trace the calculation and fix the cause. Reject invalid setups with an explicit reason.
7. **Preserve verified checkpoints.** Do not rewrite verified, frozen infrastructure (foundation,
   navigation) because you'd have designed it differently. Change it only with evidence of a real
   bug. If a change breaks an earlier verified stage, STOP and fix the regression first.
8. **Physics-driven, minimal, observable.** Every constant should have a physical reason; label
   empirical ones. Prefer small, understandable modules over frameworks/abstractions. Change one
   meaningful variable at a time, test, keep evidence. Don't build the whole architecture before
   testing behavior.
9. **Work incrementally and autonomously:** INSPECT → PLAN → IMPLEMENT → TEST → RUN → OBSERVE →
   DEBUG → VERIFY → CHECKPOINT → CONTINUE. Commit and push working increments to the branch.

---

## 3. ENVIRONMENT (verified)

- Human's machine: **Windows 11**, **Rocket League (Steam)**, **RLBot GUI**, **RLBot `1.68.0`**,
  **Python 3.11.x** (RLBotGUI ships its own Python 3.11 at
  `C:\Users\omars\AppData\Local\RLBotGUIX\Python311`).
- API style is **RLBot v4** (NOT v5): `BaseAgent`, `SimpleControllerState`, `GameTickPacket`,
  `initialize_agent()`, `get_output(packet)`. Do not migrate to v5 unless inspection proves the
  installed env changed.
- Flatbuffers pinned at **1.12** by rlbot 1.68. rlbot 1.68 uses the removed `imp` module, so it
  only runs on Python ≤3.11 — **use 3.11, never 3.13**.
- To inspect/unit-test off the game (e.g. in a Linux container): `python3.11 -m venv venv &&
  venv/bin/pip install rlbot==1.68.0 pytest`. This installs the real package so you can inspect
  types and run tests. It is NOT a substitute for physical testing.

---

## 4. CRITICAL VERIFIED FACTS — do not re-derive, do not break

### RLBot 1.68 (v4) API
- `class MyBot(BaseAgent)`. The framework constructs it as `BaseAgent.__init__(self, name, team,
  index)`. Instance attrs: `self.name` (str), `self.team` (int: **0 = blue attacks +y, 1 = orange
  attacks −y**), `self.index` (int: index into `packet.game_cars`), `self.logger`, `self.renderer`
  (a `RenderingManager`, may be set after construction).
- `initialize_agent(self)` — one-time setup hook, no packet yet.
- `get_output(self, packet: GameTickPacket) -> SimpleControllerState` — called every tick.
- `SimpleControllerState(steer, throttle, pitch, yaw, roll, jump, boost, handbrake, use_item)`.
  Floats in **[-1, 1]**: `throttle` +forward/−reverse(brake); `steer` **+ = RIGHT, − = LEFT**;
  `handbrake=True` = powerslide. Bools for jump/boost/handbrake/use_item.
- `GameTickPacket` (ctypes). Key fields:
  - `packet.num_cars`, `packet.game_cars[i]` (`PlayerInfo`): `.physics.location/velocity`
    (`Vector3` x,y,z), `.physics.rotation` (`Rotator` pitch,yaw,roll **radians**),
    `.has_wheel_contact` (bool), `.boost` (int), `.team` (ubyte), `.name`.
  - **`PlayerInfo.name` is a `c_wchar` array → already a Python `str`. NEVER call `.decode()` on
    it.** (This was a historical bug class.)
  - `packet.game_ball.physics.location/velocity`.
  - `packet.game_info`: `.seconds_elapsed` (float), `.is_round_active` (bool),
    `.is_kickoff_pause` (bool), `.frame_num` (int), etc. Use `seconds_elapsed` for timing
    (tick-rate independent). During kickoff countdown `is_round_active` is False.
- **Bot module loading:** the framework inserts the bot `.py`'s own directory onto `sys.path` and
  imports it by module name. So `src/bot.py` can do `from util.vec import Vec3` and
  `import navigation` (siblings under `src/`). Tests replicate this via `conftest.py` adding `src/`.
- **Config files** (`.cfg`, INI format). A bot cfg needs `[Locations]` with `looks_config`,
  `python_file`, `requirements_file`, `name`, `maximum_tick_rate_preference`, plus `[Details]`.
  Appearance cfg has `[Bot Loadout]`/`[Bot Loadout Orange]`/`[Bot Paint Blue]`/`[Bot Paint Orange]`.
  In RLBotGUI you add a bot by selecting its `.cfg`.
- **Rendering** (`self.renderer`, a `RenderingManager`): `begin_rendering(group_id='default')` …
  draw … `end_rendering()`. Draw methods: `draw_line_3d(v1, v2, color)`,
  `draw_rect_3d(vec, w, h, filled, color, centered=False)`, `draw_string_2d(x, y, sx, sy, text,
  color)`, `draw_string_3d(...)`, `draw_polyline_3d(...)`. Colors: `renderer.red()/lime()/cyan()/
  yellow()/white()/orange()/...`. Points may be `Vec3`, ctypes `Vector3`, or tuples (the renderer
  accepts anything subscriptable with x/y/z). Draw calls only work between begin/end; if
  `self.renderer` is None, skip.
- **RENDERING IS OFF BY DEFAULT.** In RLBot v4 the human must enable it: **press `Page Up` in the
  game** (`Page Down` disables), or tick **Extra → Enable Rendering** in RLBotGUI. If a bot's
  overlay "doesn't show," this is almost always why — not a code bug.

### Field / object constants (verified from RLBot wiki + package; in `src/field.py`)
- Side walls at **x = ±4096** (RIGHT = +x, LEFT = −x). Back walls / goals at **y = ±5120**.
  Ceiling **z = 2044**. Floor z = 0.
- **Ball radius = 92.75.** A ball resting on flat ground has center z ≈ 92.75; resting FLUSH
  against a side wall it sits higher (the wall-floor corner lifts it, observed ~150–250 uu — this
  is the ideal Kuxir height).
- Car (Octane) rest height z ≈ **17.01**; approx hitbox length 118 / width 84 / height 36.
- Goal: half-width 892.755, height 642.775.
- Axes are **LEFT-HANDED**. Consequence you must respect: for a car facing −y, its *right* vector
  is **+x** (not −x). Do not reason about left/right with right-handed intuition — use the basis
  below.

### Coordinate / steering conventions (proven; in `src/util/`)
- `Orientation(rotation)` builds the basis (c/s = cos/sin of pitch p / yaw y / roll r):
  `forward = (cp·cy, cp·sy, sp)`, `right = (cy·sp·sr − cr·sy, sy·sp·sr + cr·cy, −cp·sr)`,
  `up = (−cr·cy·sp − sr·sy, −cr·sy·sp + sr·cy, cp·cr)`. Verified orthonormal.
- `relative_location(center, ori, target)` → local vector: **x = how far AHEAD, y = how far to
  the RIGHT, z = how far ABOVE.**
- **Steering law (proven, vendored verbatim from RLBotPythonExample):**
  `heading_error = atan2(local.y, local.x)` (0 = facing target, ±π = directly behind);
  `steer = clamp(heading_error · 5, −1, 1)`. **No sign flip.** Verified: target ahead→0, right→+1,
  left→−1, directly behind→turn-around (±1). Do NOT "fix" this.

---

## 5. REPO LAYOUT

```
C:\Users\omars\source\repos\PinchBot\
├── MASTER_PROMPT.md          # this file
├── README.md                 # checkpoint ledger + physical test procedures
├── requirements.txt          # rlbot==1.68.0
├── rlbot.cfg                 # top-level match config (CLI/reference; GUI uses its own)
├── conftest.py               # puts src/ on sys.path for tests (mirrors RLBot's loader)
├── src/
│   ├── bot.py                # PinchBot — Stage 0 foundation (FROZEN). IDLE→THROTTLE→STOP proof.
│   ├── pinch_bot.cfg         # Stage 0 bot config
│   ├── appearance.cfg        # shared loadout (used by all three bots)
│   ├── navtest.py            # NavTest — Stage 1 generic navigation test bot
│   ├── navtest.cfg
│   ├── geomtest.py           # GeomTest — Stage 2 render-ONLY geometry inspection bot (no contact)
│   ├── geomtest.cfg
│   ├── field.py              # verified field/object constants + attack_sign(team)
│   ├── navigation.py         # drive_to_target(car, target, arrival_radius) — generic ground nav
│   ├── wall_pinch_geometry.py# compute_wall_pinch_setup(ball_pos, ball_vel, team) -> PinchSetup
│   └── util/
│       ├── vec.py            # Vec3 (vendored, proven)
│       ├── orientation.py    # Orientation + relative_location (vendored, proven)
│       └── drive.py          # steer_toward_target + limit_to_safe_range (vendored, proven)
└── tests/                    # 67 tests, all passing; run with pytest in the rlbot-1.68 env
    ├── fake_packet.py        # builds a real GameTickPacket struct for tests
    ├── test_stage0_foundation.py
    ├── test_util.py
    ├── test_navigation.py
    └── test_wall_pinch_geometry.py
```

Three SEPARATE bots on purpose: `bot.py` (Stage 0) and `navtest.py` (Stage 1) are FROZEN and must
keep working. Build new stages as new modules/bots; don't break the frozen ones. Run the
regression suite before and after every change.

---

## 6. CURRENT STATE — checkpoint ledger

| # | Milestone | Software | Physical (in-game) |
|---|-----------|----------|--------------------|
| 0 | RLBot foundation (loads, controls the car) | ✅ VERIFIED | ✅ VERIFIED — FROZEN |
| 1 | Generic navigation to a target (turn/drive/slow/arrive, no orbit, no blind reverse) | ✅ VERIFIED | ✅ VERIFIED — FROZEN |
| 2 | Wall-pinch SEARCH/SETUP geometry | ✅ VERIFIED | — |
| 3 | Geometry physically believable (rendered, matches field) | ✅ VERIFIED | ✅ VERIFIED |
| 4 | Car reaches the pinch setup point (STABILIZE) | — | — |
| 5 | Pinch stabilization reliable | — | — |
| 6 | First real pinch EXECUTE attempt | — | — |
| 7 | Pinch VERIFY (measure the result) | — | — |
| 8 | RECOVER / retry | — | — |
| 9 | Reliable Kuxir wall pinch | — | — |
| 10–12 | Ground → ceiling → advanced/Aztral pinches | — | — |

**You are at Checkpoint 3 → 4. Next milestone: STABILIZE (see §9). Zero intentional ball contact
until SETUP+STABILIZE are physically reliable.**

---

## 7. WHAT EACH BUILT STAGE DOES

- **Stage 0 (`bot.py`, PinchBot):** proves the full pipeline. Anchored to the first
  `is_round_active` tick via `seconds_elapsed`, it does IDLE (1.0s, throttle 0) → THROTTLE (1.5s,
  throttle 1) → STOP (coast, hold), steer 0 throughout. Telemetry every 30 ticks.
- **Stage 1 (`navigation.drive_to_target` + `navtest.py`, NavTest):** generic ground nav to a
  world point, stops cleanly within `arrival_radius`. NavTest drives to the **ball** with
  `arrival_radius ≈ 202` (stops just short, no contact).
  - Steering: the proven law above.
  - Speed: `desired = min(1410, sqrt(2·3500·remaining))` (stopping-distance), so it decelerates to
    0 at the target and holds. An **alignment speed cap** (full speed when aligned, down to
    `REORIENT_SPEED=500` when heading error ≥ ~46°) + **powerslide when badly misaligned & fast**
    keep turns tight so it **spirals in instead of orbiting**.
  - **No blind reverse:** `throttle < 0` is ONLY braking against current forward motion; a target
    behind is reached by turning around under forward throttle, never by reversing.
  - Arrival gated on **planar** speed (not just forward speed) so a sideways-sliding car isn't
    falsely "arrived".
- **Stage 2 (`wall_pinch_geometry.compute_wall_pinch_setup` + `geomtest.py`, GeomTest):**
  render-ONLY (returns an all-zero controller; never moves, never touches the ball). Computes the
  pinch SETUP from live ball state and draws it.

### The geometry (`compute_wall_pinch_setup(ball_pos, ball_vel, team) -> PinchSetup`)
Relationship is **CAR → BALL → WALL** (car on the field-interior side, wall on the far side).
- `wall`: nearer side wall from `sign(ball.x)` (RIGHT = +x plane, LEFT = −x plane).
- `wall_normal`: **inward** unit normal: RIGHT → (−1,0,0), LEFT → (+1,0,0).
- `wall_tangent`: horizontal along-wall unit (0, ±1, 0). Sign = desired exit: `sign(ball_vel.y)`
  if `|ball_vel.y| > TANGENT_VEL_THRESHOLD`, else `attack_sign(team)`.
- `approach_direction = normalize(−wall_normal + wall_tangent)` (≈45° diagonal: into the wall AND
  along the exit). Depends ONLY on wall+team+ball_vel — never on the car, so the rendered setup is
  steady as the car moves.
- `contact_point = ball − approach_direction · BALL_RADIUS` (ball surface facing the car).
- `approach_point = ball − approach_direction · (BALL_RADIUS + APPROACH_STANDOFF)`, z set to
  `CAR_REST_Z` (the car's ground setup point; hand this to `drive_to_target`).
- `expected_pinch_direction = wall_tangent` (ball exits along the wall).
- **Validation layer** (first failing reason wins; never a clamped/nonsense target). Rejection
  reasons: `non_finite_input`, `ball_outside_field`, `ball_near_corner` (|y| > CORNER_Y_LIMIT, the
  rounded corner breaks the flat-wall model), `ball_not_near_wall`, `ball_too_high`,
  `ball_leaving_wall` (ball rushing off the wall toward midfield: `ball_vel·wall_normal >
  BALL_LEAVE_WALL_SPEED`), `approach_dir_degenerate`, `target_out_of_bounds`,
  `target_too_far_from_ball`.

### Current tuned constants (empirical, set from in-game feedback — the human is the authority)
- `wall_pinch_geometry.py`: `NEAR_WALL_THRESHOLD = 150.0` (ball must be essentially ON the wall —
  surface within 150 uu of the wall plane; lower = stricter), `MAX_PINCH_HEIGHT = 500.0`,
  `CORNER_Y_LIMIT = 4000.0`, `APPROACH_STANDOFF = 400.0`, `TANGENT_VEL_THRESHOLD = 200.0`,
  `BALL_LEAVE_WALL_SPEED = 800.0`, `MAX_TARGET_DIST = 2000.0`, `FIELD_MARGIN = 100.0`.
- `navigation.py`: `MAX_DRIVE_SPEED=1410`, `BRAKE_DECEL=3500`, `DEFAULT_ARRIVAL_RADIUS=120`,
  `HOLD_SPEED=40`, `THROTTLE_DEADZONE=50`, `STEER_GAIN=5`, `FACING_ANGLE=π/2`, `ALIGN_ANGLE=0.35`,
  `REORIENT_ANGLE=0.80`, `REORIENT_SPEED=500`, `POWERSLIDE_MIN_SPEED=400`.

---

## 8. BUGS ALREADY FOUND & FIXED (do not reintroduce)

1. **Navigation orbited nearby off-axis targets** — a fixed high turn-speed meant the turn radius
   exceeded the arrival radius, so the car circled forever. Fixed with the alignment speed cap +
   powerslide. (Lesson: at speed v the RL turn radius grows; to reach an off-axis target you must
   slow down. Steering-only has a ~145 uu minimum radius.)
2. **Lateral-slide false arrival** — arrival judged by forward speed only; fixed to use planar
   speed.
3. **Pinch height ceiling too tight** — a "ball bottom within car height" formula (~129) rejected
   valid low pinches, because a ball flush against the wall sits ~150–250 uu up. Replaced with an
   empirical ceiling (now 500). (Lesson: the wall-floor corner lifts the ball; the game decides
   reachable heights, not a napkin formula.)
4. **Near-wall gate too loose** — a 900 uu gap called the ball "near the wall" when it was clearly
   off it. Tightened to 150. (Lesson: a pinch needs the ball ON the wall.)

Recurring lesson: **constants are physical and get tuned from in-game telemetry, not guessed once.
When the human reports behavior that contradicts a constant, the game wins — fix the constant and
add a regression test.**

---

## 9. WHAT TO DO NEXT — Checkpoint 4/5: STABILIZE

Build the state machine toward: **SEARCH → SETUP → STABILIZE → EXECUTE → VERIFY → RECOVER/RETRY.**
Only SEARCH/SETUP exist (as the geometry). Next is **STABILIZE**: a bot that uses the geometry to
pick a viable setup and **drives the car to the `approach_point` and holds it**, converging —
**still with ZERO intentional ball contact** (approach the setup point, not the ball).

Suggested approach:
1. New bot (e.g. `stabilize_test.py` + `.cfg`, name `StabilizeTest`), reusing
   `compute_wall_pinch_setup` + `navigation.drive_to_target`. Keep `geomtest`/`navtest`/`bot`
   frozen.
2. Each tick: compute the setup. If viable, `drive_to_target(car, setup.approach_point,
   arrival_radius=...)` and render the setup + the car's progress. If not viable, hold still and
   render the reject reason.
3. Track and telemeter: car→target distance, heading error, velocity_toward_target, ball-wall
   gap, whether the setup is still viable. The state must **actually converge** (distance trends
   down, heading error shrinks). Abort/regenerate if: distance repeatedly increases, heading
   diverges, the ball leaves the wall, or the setup becomes invalid. **Never sit in STABILIZE
   forever, and never advance to EXECUTE just because a timer expired** — advance on live geometry.
4. Unit-test it (fake packets), framework-load-test it, then give the human an exact physical test
   (e.g. "place the ball on the right wall; the bot should drive to the lime setup point near the
   ball and stop there without hitting the ball; move the ball and it re-stabilizes"). Mark
   physically VERIFIED only after they confirm.

Then, in order, each gated by a physical test: **EXECUTE** (first intentional contact — reason
about relative velocity, approach angle, contact timing from live state; NOT "throttle=1 at the
ball"), **VERIFY** (measure ball speed/vector before vs after, exit direction, classify
MISS/NORMAL_CONTACT/SOFT_CONTACT/POSSIBLE_PINCH/PINCH_CONFIRMED/UNVERIFIED — be conservative),
**RECOVER/RETRY** (survive misses, discard stale targets, regenerate), then **reliability** across
positions/speeds/both teams. Only after a reliable wall pinch: ground → ceiling → advanced pinches
using the same principles.

---

## 10. HOW TO DEVELOP & TEST

- **Unit tests (software):** in the rlbot-1.68 Python 3.11 env, from the repo root run
  `python -m pytest`. 67 tests currently pass. Add tests for every new behavior and every bug you
  fix. `tests/fake_packet.py::make_packet(...)` builds a real `GameTickPacket` for tests.
- **Framework-load check** (catches cfg/import/class-discovery errors without the game):
  `get_bot_config_bundle(cfg)` → `import_class_with_base(bundle.python_file, BaseAgent)` →
  construct → run one `get_output` with a fake packet.
- **Physical test (human, Windows):** RLBotGUI → add bot from its `.cfg` → Free Play/Exhibition →
  **press Page Up to enable rendering** → observe. Always state the exact expected behavior and
  ask them to paste a few telemetry lines.
- **Git:** branch `claude/sweet-mendel-b2c8sv`. Commit working increments with clear messages and
  `git push -u origin claude/sweet-mendel-b2c8sv`. Do not open a PR unless asked. If the human has
  local edits to a constant you also change, tell them to `git checkout -- <file>` or `git stash`
  before pulling to avoid a conflict.

---

## 11. REPORTING FORMAT (end of each work session)

CURRENT MILESTONE · VERIFIED/UNVERIFIED · WHAT YOU INSPECTED · WHAT YOU CHANGED · FILES CHANGED ·
SOFTWARE TESTS (passed/failed/not run) · PHYSICAL RL TEST (performed or not; exact observed
result) · KNOWN ISSUES · NEXT MILESTONE. Never inflate. If uncertain, say `UNVERIFIED`.

---

## 12. HARD DON'TS
Don't invent APIs or assume v5. Don't `.decode()` a str packet field. Don't swallow exceptions.
Don't clamp nonsense targets. Don't blind-reverse or orbit in navigation. Don't drive into the
ball before EXECUTE. Don't call anything gameplay-`VERIFIED` without a human in-game test. Don't
rewrite frozen Stage 0/1 without evidence. Don't change five constants at once. Don't claim you
saw the game.
```
