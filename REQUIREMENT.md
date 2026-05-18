# CoC Tools Unified Requirements

This is the single source of truth for repository requirements.

Enforcement:

- Local gate script: `python scripts/requirement_check.py`
- CI gate workflow: `.github/workflows/requirement-gate.yml`

## 1. Scope

- Repository: `coc-tools`
- Runtime app: `coc_bot`
- Platform: Windows + ADB-compatible emulator/device
- Language: Python 3.9+

## 2. Runtime Dependencies

- `pure-python-adb==0.3.0.dev0`
- `opencv-python>=4.5.0`
- `numpy>=1.20.0`
- `easyocr>=1.6.0`

## 3. Project Structure (Required)

- `coc_bot/main.py`: runtime entrypoint
- `coc_bot/settings.json`: runtime settings
- `coc_bot/core/`: device, vision, ui, logging, humanize core
- `coc_bot/screens/`: screen abstraction layer
- `coc_bot/assets/`: template resources
- `coc_bot/logs/`: runtime/debug outputs

## 4. Device & Emulator Requirements

1. Bot must bootstrap device via profile (`bluestacks`, `ldplayer`, `nox`, `mumu`, `android_emulator`, `usb_or_existing`, `custom_endpoint`).
2. Profile selection flow:
- default quick path: press `Enter` to keep current profile.
- change path: type `c`, then select profile.
3. If emulator profile is selected, bot must ensure emulator process is running before ADB checks.
4. Bot must verify ADB device availability before main loop.
5. If device resolution/serial cannot be resolved, bot must fallback to setup wizard.

## 5. CoC App State Requirements

1. Bot must check `is_package_installed("com.supercell.clashofclans")` before app-state logic.
2. `is_app_running` must use strict signals (foreground/process), not broad string matches that can false-positive during Play Store install.
3. If CoC is not installed, bot must stop with a single actionable error message.
4. If app cannot be brought to foreground, bot must stop instead of continuing recognition loop.

## 6. Vision & Recognition Requirements

1. All assets must be preloaded into RAM (`vision.load_assets`) before operational loops.
2. Critical screen detection must use strict anchors and avoid permissive fallback that causes false positives.
3. `wait_until_appears` must support:
- timeout
- optional silent mode
- optional ORB fallback toggle
4. Timeouts should save debug screenshots to `coc_bot/logs/debug`.

## 7. Core Performance Requirements

1. Screen capture path must avoid disk I/O in operational loops.
2. Asset caching is mandatory; do not call `cv2.imread()` inside action loops.
3. Smart waiting is mandatory for UI transitions; avoid fixed sleep-only flow.
4. Runtime should fail fast when device/app prerequisites are not met.

## 8. Anti-Detection / Humanization Requirements

1. Tap/click must support coordinate jitter (never hard center-only interactions).
2. Delay model must be randomized from config ranges.
3. Swipe movement should support human-like curves for line deployments.
4. Input path should prefer robust device interaction primitives; avoid brittle fixed-timing assumptions.
5. Preferred roadmap for input backend: support hardware-like input option (scrcpy HID/minitouch) as an upgrade path from `adb shell input`.

## 9. Screen Object Model Requirements

1. Each screen object must implement `is_current_screen()`.
2. Screen identification must rely on stable anchor combinations.
3. Shared popup handling must remain centralized in base screen layer.

## 10. Task & Loop Control Requirements

1. Decision thresholds and tunables must be in `settings.json` (no hardcoded combat economy constants).
2. Unknown/failed recognition states should trigger safe recovery paths.
3. Main loop should behave as a state machine (connect -> validate state -> act -> recover/fallback).

## 11. Asset Naming Convention (Mandatory)

1. Filenames must be lowercase `snake_case`.
2. Allowed characters in basename: `a-z`, `0-9`, `_`.
3. No spaces, no special characters, no extra dots in basename.
4. Extension: `.png` for recognition templates.
5. Basename uniqueness:
- must be globally unique for critical anchors.
- if duplicate basename exists, code must use path-qualified keys.
6. Variant naming:
- use `_v2`, `_v3`, `_alt1`, `_alt2`
- avoid names like `copy`, `new`, `final`.

## 12. Logging Requirements

1. Logging config must be centralized and reusable (`coc_bot/core/logging_utils.py`).
2. Format: only level tag is colorized, message keeps default terminal color.
3. Normal path logs should stay concise.
4. Internal retries/noisy diagnostics should be `DEBUG` level.
5. Errors must be actionable and non-duplicated.

## 13. Screen Layer Requirements

1. `BaseScreen` provides shared popup handling/recovery helpers.
2. Each screen class must implement `is_current_screen()`.
3. Home detection must avoid single-anchor permissive detection.

## 14. Humanization Requirements

1. Click/tap coordinates must support jitter.
2. Delays should support randomized ranges from settings.
3. Swipe path should support humanized curve generation.

## 15. Settings Contract (`coc_bot/settings.json`)

Must contain and maintain:

- `device.profile`
- `device.endpoint`
- `device.serial`
- `device.auto_select_single`
- `device.auto_launch_profile` (if retained by runtime behavior)
- farm thresholds
- delay ranges
- jitter radius

## 16. Quality Gates Before Merge

1. Bot starts and resolves profile/device path without manual code change.
2. If CoC missing: single clear install error, no contradictory logs.
3. No false-positive home detection on emulator launcher/store screens.
4. Asset names for newly added templates must pass naming rules.
5. No duplicate/contradictory high-level error logs for one failure.
6. Runtime loop must not continue when app foreground validation fails.
7. Recognition anchors for critical screens must be validated against negative screens (launcher/store).
8. Runtime-generated debug artifacts under `coc_bot/logs/` must not be committed (enforced by `.gitignore`).

## 17. Milestone Delivery Order (Implementation Planning)

1. Device bootstrap + profile resolution + connection fail-safe.
2. Vision reliability baseline (anchor strictness + false-positive controls).
3. Stable home-screen actions and recovery behavior.
4. Expanded task modules only after core detection stability is validated.

## 18. Backward Compatibility Policy

1. Keep current operational behavior stable unless explicitly changed.
2. For strictness upgrades (state detection, anchors), prefer fail-safe stop over unsafe continuation.
3. Changes to template keys must include migration/update in caller code.
