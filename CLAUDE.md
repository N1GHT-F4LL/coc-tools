# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Windows-targeted Clash of Clans automation bot. Drives an ADB-connected Android emulator (BlueStacks / LDPlayer / Nox / MuMu / Android Emulator) or USB device through screen-capture + template-matching computer vision. Python 3.9+.

## Common commands

```bash
# Install runtime deps
pip install -r requirements.txt

# Run the bot (always invoke from repo root — settings/asset paths are relative)
python coc_bot/main.py

# Requirement gate (run before any PR). Mirrors CI in .github/workflows/requirement-gate.yml
python scripts/requirement_check.py
python scripts/requirement_check.py --strict-assets   # only when cleaning legacy asset names

# Debug helpers
python scripts/debug_tools.py capture                # save current device screen to coc_bot/logs/debug/
python scripts/debug_tools.py assets                 # list every key in the vision asset cache
python scripts/debug_tools.py assets <keyword>       # filter cache keys (e.g. "btn_", "icon_", "close")
python scripts/capture.py                            # wake → launch CoC → screenshot after 15s
```

There is no test suite. "Tests" are the requirement gate plus manual run-through.

## Authoritative requirements doc

`REQUIREMENT.md` is the single source of truth for architecture, settings contract, naming, and merge gates. PR descriptions are expected to map changes back to its sections (see `CONTRIBUTING.md`). When changing anything device-, vision-, or settings-related, re-read the relevant `REQUIREMENT.md` section before editing — it encodes past incidents (e.g. permissive home detection, false-positive app-running checks).

## Architecture

Runtime flow lives in `coc_bot/main.py` and is a deliberate state machine: **connect → validate app state → act → recover/fallback**. Each stage gates the next; failures must stop the loop rather than continue with degraded state (see `REQUIREMENT.md` §5, §16).

1. `load_settings()` reads `coc_bot/settings.json`.
2. `bootstrap_device(settings, save_settings, logger)` (in `core/device.py`) does interactive profile selection, optionally launches the emulator executable, connects ADB, picks a shell-healthy serial, and persists the resolved serial back to settings.
3. `device.ensure_coc_ready(...)` enforces install + foreground checks for `com.supercell.clashofclans` before any recognition runs.
4. `vision.load_assets("coc_bot/assets")` preloads every PNG into RAM (mandatory — `cv2.imread` in action loops is forbidden, §7).
5. Main loop instantiates a `HomeScreen` and alternates between `is_current_screen()` → actions and `close_popups()` recovery.

### `coc_bot/core/`

- **`device.py`** is the largest and most defensive module. Key concepts:
  - `PROFILE_ENDPOINTS` / `PROFILE_EXECUTABLES` / `PROFILE_PROCESS_NAMES` map each emulator profile to its known ADB ports, install paths, and `tasklist` process names. Add new emulators here.
  - BlueStacks dual-endpoint instability is a recurring failure mode. `pick_healthy_serial()`, `_run_shell_with_failover()`, and `try_recover_adb_transport()` exist specifically to detect `error: closed` shell transports and silently switch to an alternate serial — preserve this behavior when refactoring.
  - `is_app_running` deliberately uses foreground/pidof/ps signals, NOT broad string matches against `dumpsys activity`. The latter false-positives during Play Store installs (§5.2). Do not "simplify" this.
  - `is_package_installed` returns tri-state `True | False | None` (None = ADB shell unstable, can't tell). Callers (`ensure_coc_ready`, `launch_game`) must handle None as a hard stop, not as "not installed".
  - `bootstrap_device` may rewrite `settings["device"]["serial"]` via the injected `save_settings` callback. Anything that reads serial after bootstrap should re-read settings or use `device.serial`.

- **`vision.py`** exposes a module-level singleton `vision`. Cache keys are stored under **both** the file stem (e.g. `icon_attack`) and the path-qualified relative key (e.g. `ui/btn_close`). Use stem keys for shared anchors and rel-path keys when basenames collide (§11.5). `find_template` runs `cv2.matchTemplate` first; if confidence < threshold and `use_orb_fallback=True`, falls back to ORB+FLANN feature matching with homography. Pass `use_orb_fallback=False` for strict anchor checks where false positives are unacceptable (home detection does this).

- **`ui_manager.py`** is the only layer screens should use to interact with the device. `wait_until_appears(name, timeout, silent, use_orb_fallback)` is the canonical wait primitive — it writes a debug screenshot to `coc_bot/logs/debug/timeout_<name>_<ts>.png` whenever it times out. `click()` always routes through `humanize.get_jittered_coords()` (§8.1, §14.1).

- **`humanize.py`** holds the jitter radius (from `settings.jitter.radius`) and a quadratic Bezier path generator for swipes. Currently `device.swipe` only uses the path's endpoints — the bezier output is plumbed but the input backend doesn't consume the intermediate points yet (§8.5 calls this out as a roadmap item: scrcpy HID / minitouch).

- **`logging_utils.py`** — `setup_logging(level)` is the only place that should configure the root logger. Format rule: only the `[LEVEL]` tag is ANSI-colored; the message keeps the terminal default (§12.2).

### `coc_bot/screens/`

- `BaseScreen` provides shared `close_popups()` (probes generic `btn_close`/`btn_okay`/`btn_ok` with 0.2s timeouts).
- Every screen must implement `is_current_screen()` using **strict multi-anchor** detection — `HomeScreen` requires ≥2 of `icon_attack`/`btn_attack`/`attack` to match, ORB fallback **off**. Single-anchor permissive detection is explicitly banned (§13.3, §16.3) because it false-positives on emulator launchers and the in-game store.

### `coc_bot/assets/`

Recognition templates. Naming rule (§11) is enforced by the requirement gate in warn mode by default, error mode under `--strict-assets`:
- lowercase `snake_case`, `[a-z0-9_]+` only
- no spaces, dashes, dots in basename (except the `.png` extension)
- variants: `_v2`, `_alt1`, never `copy`/`new`/`final`
- basenames should be globally unique for critical anchors; if duplicate, code must use the rel-path key.

The repo currently contains legacy assets that violate these rules — leave them unless explicitly doing an asset cleanup pass.

## Settings contract

`coc_bot/settings.json` keys checked by `scripts/requirement_check.py` (any missing key fails the gate):

```
device.{profile, endpoint, serial, auto_select_single}
farm.{min_gold, min_elixir, min_dark_elixir}
delays.{short_min, short_max, long_min, long_max}
jitter.radius
```

Tunables (farm thresholds, delay ranges, jitter) must live here — do not hardcode them in code (§10.1).

## Runtime artifacts

`coc_bot/logs/` (and `coc_bot/logs/debug/`) hold runtime screenshots written by `wait_until_appears` timeouts, `main.py`'s initial-screen capture, and the debug tools. They are `.gitignore`d and the requirement gate verifies that. Never commit anything under `coc_bot/logs/`.

## Things to preserve when editing

- The `is_app_running` strictness — see §5.2.
- BlueStacks failover paths in `device.py` (`_run_shell_with_failover`, `pick_healthy_serial`, `try_recover_adb_transport`).
- Multi-anchor strict screen detection (no permissive fallback for critical screens).
- Asset preloading via `vision.load_assets`; no `cv2.imread` calls inside operational loops.
- The tri-state return of `is_package_installed`.
- Settings keys listed in the contract above — adding or removing one requires updating both `requirement_check.py` and `REQUIREMENT.md` §15.
