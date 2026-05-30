import subprocess
import time
import os

from .device import (
    Device,
    PROFILE_ENDPOINTS,
    PROFILE_EXECUTABLES,
    PROFILE_PROCESS_NAMES,
)


def connect_with_profile(device, profile, endpoint=None):
    device.start_adb_server()
    if profile == "custom_endpoint" and endpoint:
        device.connect_device(endpoint)
        return
    for ep in PROFILE_ENDPOINTS.get(profile, []):
        device.connect_device(ep)


def launch_emulator_for_profile(profile, logger, override_path=None):
    if override_path and os.path.exists(override_path):
        paths = [override_path]
    else:
        paths = PROFILE_EXECUTABLES.get(profile, [])
    for exe in paths:
        if os.path.exists(exe):
            try:
                subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                logger.info(f"Starting emulator for profile '{profile}'...")
                return True
            except Exception as e:
                logger.warning(f"Failed to launch emulator at {exe}: {e}")
    return False


def is_emulator_running(profile):
    names = PROFILE_PROCESS_NAMES.get(profile, [])
    if not names:
        return False
    for name in names:
        try:
            res = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {name}"],
                capture_output=True,
                text=True,
            )
            out = (res.stdout or "").lower()
            if name.lower() in out:
                return True
        except Exception:
            continue
    return False


def ensure_emulator_running(profile, logger, override_path=None):
    if profile not in PROFILE_PROCESS_NAMES:
        return True
    if is_emulator_running(profile):
        logger.debug(f"Emulator process for profile '{profile}' is already running.")
        return True
    logger.info(f"Emulator for profile '{profile}' is not running.")
    launched = launch_emulator_for_profile(profile, logger, override_path=override_path)
    if launched:
        logger.debug(f"Waiting 12 seconds for {profile} startup...")
        time.sleep(12)
        return True
    logger.warning(f"Could not auto-launch emulator for profile '{profile}'.")
    return False


def select_ready_device_interactive(devices, logger):
    ready_devices = [d for d in devices if d.get("state") == "device"]
    blocked_devices = [d for d in devices if d.get("state") != "device"]

    logger.info("Detected devices:")
    for idx, d in enumerate(devices, 1):
        logger.info(f"{idx}. {d['serial']} ({d['state']})")

    if blocked_devices:
        logger.warning("Some devices are not ready. State should be 'device'.")
        logger.warning("If 'unauthorized', unlock device/emulator and accept RSA prompt.")

    if not ready_devices:
        return None

    logger.info("Selectable devices:")
    for idx, d in enumerate(ready_devices, 1):
        logger.info(f"{idx}. {d['serial']}")

    choice = input(f"Select device [1-{len(ready_devices)}] (Enter=1): ").strip()
    if not choice:
        return ready_devices[0]["serial"]
    if not choice.isdigit():
        return None
    selected_idx = int(choice)
    if selected_idx < 1 or selected_idx > len(ready_devices):
        return None
    return ready_devices[selected_idx - 1]["serial"]


def run_device_setup_wizard(device, settings, save_settings, logger):
    logger.info("Starting device setup wizard...")
    logger.info("Choose profile:")
    profile_options = [
        ("ldplayer", "LDPlayer"),
        ("bluestacks", "BlueStacks"),
        ("nox", "Nox"),
        ("mumu", "MuMu"),
        ("android_emulator", "Android Emulator"),
        ("usb_or_existing", "USB / Already listed in adb devices"),
        ("custom_endpoint", "Custom ADB endpoint (ip:port)"),
    ]
    for idx, (_, label) in enumerate(profile_options, 1):
        logger.info(f"{idx}. {label}")

    raw = input(f"Select profile [1-{len(profile_options)}] (Enter=1): ").strip()
    if not raw:
        profile_idx = 1
    elif raw.isdigit() and 1 <= int(raw) <= len(profile_options):
        profile_idx = int(raw)
    else:
        logger.error("Invalid profile choice.")
        return False

    selected_profile = profile_options[profile_idx - 1][0]
    custom_endpoint = ""
    if selected_profile == "custom_endpoint":
        custom_endpoint = input("Enter endpoint (example 127.0.0.1:5555): ").strip()
        if not custom_endpoint:
            logger.error("Custom endpoint is required.")
            return False
    elif selected_profile in ("ldplayer", "bluestacks", "nox", "mumu", "android_emulator"):
        ensure_emulator_running(selected_profile, logger)

    logger.info(f"Applying profile: {selected_profile}")
    connect_with_profile(device, selected_profile, custom_endpoint)
    time.sleep(1.0)
    devices = device.list_devices()
    if not devices:
        retry = input("No devices yet. Wait more 20s and retry scan? [Y/n]: ").strip().lower()
        if retry in ("", "y", "yes"):
            time.sleep(20)
            connect_with_profile(device, selected_profile, custom_endpoint)
            time.sleep(1.0)
            devices = device.list_devices()
    if not devices:
        logger.error("No ADB devices found after applying profile.")
        return False

    selected_serial = select_ready_device_interactive(devices, logger)
    if not selected_serial:
        logger.error("No valid ready device selected.")
        return False

    settings.setdefault("device", {})
    settings["device"]["profile"] = selected_profile
    settings["device"]["endpoint"] = custom_endpoint
    settings["device"]["serial"] = selected_serial
    settings["device"]["auto_select_single"] = True
    save_settings(settings)

    device.serial = selected_serial
    logger.info(f"Device selected and saved: {selected_serial}")
    return True


def choose_profile_interactive(settings, save_settings, logger, non_interactive=False):
    device_cfg = settings.setdefault("device", {})
    current_profile = device_cfg.get("profile", "usb_or_existing")
    profile_options = [
        ("ldplayer", "LDPlayer"),
        ("bluestacks", "BlueStacks"),
        ("nox", "Nox"),
        ("mumu", "MuMu"),
        ("android_emulator", "Android Emulator"),
        ("usb_or_existing", "USB / Already listed in adb devices"),
        ("custom_endpoint", "Custom ADB endpoint (ip:port)"),
    ]
    label_map = {key: label for key, label in profile_options}
    current_label = label_map.get(current_profile, current_profile)

    logger.info(f"Current profile: {current_label}")
    if non_interactive:
        return current_profile
    choice_mode = input("Press Enter to continue, or type 'c' to change profile: ").strip().lower()
    if choice_mode != "c":
        return current_profile

    for idx, (_, label) in enumerate(profile_options, 1):
        logger.info(f"{idx}. {label}")

    raw = input(f"Select profile [1-{len(profile_options)}] (Enter={current_label}): ").strip()
    if not raw:
        return current_profile
    if not raw.isdigit() or not (1 <= int(raw) <= len(profile_options)):
        logger.warning("Invalid profile choice. Using default profile from settings.")
        return current_profile

    selected_profile = profile_options[int(raw) - 1][0]
    if selected_profile != current_profile:
        device_cfg["profile"] = selected_profile
        device_cfg["serial"] = ""
        if selected_profile != "custom_endpoint":
            device_cfg["endpoint"] = ""
        save_settings(settings)
        logger.info(f"Profile switched to: {selected_profile}")

    if selected_profile == "custom_endpoint":
        endpoint = input("Enter endpoint (example 127.0.0.1:5555, Enter=keep current): ").strip()
        if endpoint:
            device_cfg["endpoint"] = endpoint
            save_settings(settings)

    return device_cfg.get("profile", selected_profile)


def bootstrap_device(settings, save_settings, logger, non_interactive=False):
    device_cfg = settings.get("device", {})
    profile = choose_profile_interactive(settings, save_settings, logger,
                                         non_interactive=non_interactive)
    device_cfg = settings.get("device", {})
    endpoint = device_cfg.get("endpoint", "")
    preferred_serial = device_cfg.get("serial")
    auto_select_single = device_cfg.get("auto_select_single", True)
    strict_serial = device_cfg.get("strict_serial", True)
    configured_adb_path = device_cfg.get("adb_path", "")
    adb_path = configured_adb_path or None

    device = Device(
        serial=preferred_serial,
        strict_serial=strict_serial,
        adb_path=adb_path,
        profile=profile,
        endpoint=endpoint,
    )
    if not getattr(device, "available", False):
        logger.error("\n'adb' not found in your PATH. The bot requires adb to interact with a device.")
        logger.error("Install Android platform-tools and ensure 'adb' is on your PATH, then re-run this script.")
        logger.error("On Windows, you can download from: https://developer.android.com/studio/releases/platform-tools")
        return None

    emulator_path = device_cfg.get("emulator_path", "")
    if profile in ("ldplayer", "bluestacks", "nox", "mumu", "android_emulator"):
        ensure_emulator_running(profile, logger, override_path=emulator_path or None)

    connect_with_profile(device, profile, endpoint)
    time.sleep(0.5)

    healthy = device.pick_healthy_serial(preferred_serial=device.serial)
    if not healthy:
        logger.warning("No healthy ADB shell serial detected. Attempting ADB transport recovery...")
        device.try_recover_adb_transport(profile=profile, endpoint=endpoint)
        healthy = device.pick_healthy_serial(preferred_serial=device.serial)

    if healthy and healthy != device.serial:
        logger.warning(f"Configured serial is unstable. Switching to healthy serial: {healthy}")
        device.serial = healthy
        settings.setdefault("device", {})
        settings["device"]["serial"] = healthy
        save_settings(settings)
    elif not healthy:
        logger.error("ADB shell transport is unstable on all detected serials.")
        logger.error("Please restart BlueStacks instance and run the bot again.")
        return None

    if not device.select_device(preferred_serial=preferred_serial, auto_select_single=auto_select_single):
        logger.error("Could not resolve target device from settings.")
        if non_interactive:
            logger.error("Non-interactive mode: skipping wizard. Check device.serial in settings.json.")
            return None
        should_run_wizard = input("Run device setup wizard now? [Y/n]: ").strip().lower()
        if should_run_wizard not in ("", "y", "yes"):
            logger.error("Setup aborted. Please set device.serial in settings.json.")
            return None
        if not run_device_setup_wizard(device, settings, save_settings, logger):
            logger.error("Device setup wizard failed.")
            return None

    if device.serial and device.serial != preferred_serial:
        settings.setdefault("device", {})
        settings["device"]["serial"] = device.serial
        save_settings(settings)
        logger.debug(f"Saved selected device serial to settings: {device.serial}")

    if not device.ensure_connection(retries=3, retry_delay=1.5):
        logger.error("No usable ADB device found after retries.")
        logger.debug("Falling back to setup wizard...")
        if not run_device_setup_wizard(device, settings, save_settings, logger):
            logger.error("Device setup wizard failed.")
            return None
        if not device.ensure_connection(retries=3, retry_delay=1.5):
            logger.error("Still no usable ADB device after wizard.")
            return None

    if device_cfg.get("enforce_resolution"):
        target_res = device_cfg.get("target_resolution")
        target_density = device_cfg.get("target_density")
        if target_res:
            device.enforce_resolution(target_res, target_density)
        else:
            logger.warning("enforce_resolution is true but device.target_resolution is unset; skipping.")

    return device
