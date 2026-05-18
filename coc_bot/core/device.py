import subprocess
import cv2
import numpy as np
import time
import shutil
import logging
import os

logger = logging.getLogger(__name__)

PROFILE_ENDPOINTS = {
    "android_emulator": ["127.0.0.1:5555", "127.0.0.1:5554"],
    "ldplayer": ["127.0.0.1:5555", "127.0.0.1:16384"],
    "bluestacks": ["127.0.0.1:5555", "127.0.0.1:21503"],
    "nox": ["127.0.0.1:62001"],
    "mumu": ["127.0.0.1:7555"],
}

PROFILE_EXECUTABLES = {
    "ldplayer": [
        r"C:\LDPlayer\LDPlayer9\dnplayer.exe",
        r"C:\Program Files\LDPlayer\LDPlayer9\dnplayer.exe",
    ],
    "bluestacks": [
        r"C:\Program Files\BlueStacks_nxt\HD-Player.exe",
        r"C:\Program Files\BlueStacks\HD-Player.exe",
    ],
    "nox": [
        r"C:\Program Files\Nox\bin\Nox.exe",
        r"C:\Program Files (x86)\Nox\bin\Nox.exe",
    ],
    "mumu": [
        r"C:\Program Files\Netease\MuMuPlayer-12.0\shell\MuMuPlayer.exe",
        r"C:\Program Files\Netease\MuMuPlayerGlobal-12.0\shell\MuMuPlayerGlobal.exe",
    ],
    "android_emulator": [
        r"C:\Users\Public\Android\Sdk\emulator\emulator.exe",
    ],
}

PROFILE_PROCESS_NAMES = {
    "ldplayer": ["dnplayer.exe"],
    "bluestacks": ["HD-Player.exe"],
    "nox": ["Nox.exe"],
    "mumu": ["MuMuPlayer.exe", "MuMuPlayerGlobal.exe"],
    "android_emulator": ["emulator.exe"],
}

class Device:
    def __init__(self, serial=None):
        self.serial = serial
        # Detect adb binary path early to avoid FileNotFoundError on subprocess.
        self.adb_path = shutil.which("adb")
        self.available = bool(self.adb_path)
        self.connected = False
        self.last_status_reason = "unknown"
        if not self.available:
            logger.warning("'adb' not found in PATH. Device operations will be disabled.")
            logger.info("To enable device control, install Android platform-tools and add 'adb' to your PATH.")
        # Note: avoid performing heavy side-effects at import-time.
        # Initialization will not automatically check connection or wake the
        # screen; callers should invoke those explicitly if desired.

    def _adb_cmd(self, args):
        if not self.available:
            raise FileNotFoundError("adb binary not found in PATH")
        cmd = [self.adb_path]
        if self.serial:
            cmd.extend(['-s', self.serial])
        cmd.extend(args)
        return cmd

    def _run_adb(self, args, text=True):
        if not self.available:
            return None
        try:
            return subprocess.run(
                self._adb_cmd(args),
                capture_output=True,
                text=text,
            )
        except FileNotFoundError:
            self.connected = False
            self.last_status_reason = "adb_missing"
            return None

    def _has_usable_device(self, devices_output):
        lines = [line.strip() for line in devices_output.splitlines()[1:] if line.strip()]
        if not lines:
            self.last_status_reason = "no_devices"
            return False

        if self.serial:
            for line in lines:
                if line.startswith(f"{self.serial}\tdevice"):
                    self.last_status_reason = "ok"
                    return True
            self.last_status_reason = "serial_not_found_or_unauthorized"
            return False

        for line in lines:
            if line.endswith("\tdevice"):
                self.last_status_reason = "ok"
                return True

        self.last_status_reason = "unauthorized_or_offline"
        return False

    def list_devices(self):
        """
        Return parsed output of `adb devices`:
        [{"serial": "...", "state": "device|offline|unauthorized"}]
        """
        if not self.available:
            return []
        res = self._run_adb(['devices'])
        if res is None or res.returncode != 0:
            self.last_status_reason = "adb_command_failed"
            return []

        devices = []
        lines = [line.strip() for line in res.stdout.splitlines()[1:] if line.strip()]
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                devices.append({"serial": parts[0], "state": parts[1]})
        return devices

    def start_adb_server(self):
        if not self.available:
            return False
        res = self._run_adb(['start-server'])
        return bool(res and res.returncode == 0)

    def connect_device(self, endpoint):
        if not self.available:
            return False
        res = self._run_adb(['connect', endpoint])
        if res is None:
            return False
        out = (res.stdout or "") + (res.stderr or "")
        out = out.lower()
        return ("connected to" in out) or ("already connected to" in out)

    def try_connect_common_emulators(self):
        """
        Try common local emulator ADB endpoints.
        Returns number of successful/known connections.
        """
        endpoints = [
            "127.0.0.1:5555",  # standard Android emulator
            "127.0.0.1:5554",
            "127.0.0.1:7555",  # MuMu
            "127.0.0.1:62001", # Nox
            "127.0.0.1:16384", # LDPlayer variants
            "127.0.0.1:21503", # BlueStacks Hyper-V variants
        ]
        hits = 0
        for ep in endpoints:
            if self.connect_device(ep):
                hits += 1
        return hits

    def select_device(self, preferred_serial=None, auto_select_single=True):
        """
        Pick a target device and assign self.serial.
        Returns True when a usable target is selected.
        """
        devices = self.list_devices()
        ready_devices = [d for d in devices if d["state"] == "device"]

        if preferred_serial:
            for d in ready_devices:
                if d["serial"] == preferred_serial:
                    self.serial = preferred_serial
                    return True
            self.last_status_reason = "preferred_serial_not_ready"
            return False

        if auto_select_single and len(ready_devices) == 1:
            self.serial = ready_devices[0]["serial"]
            logger.info(f"Auto-selected ADB device: {self.serial}")
            return True

        if len(ready_devices) == 0:
            self.last_status_reason = "no_ready_device"
            return False

        # Multiple ready devices but no explicit serial configured.
        self.last_status_reason = "multiple_devices_require_serial"
        logger.error("Multiple ADB devices detected. Please set device.serial in settings.json")
        for d in ready_devices:
            logger.error(f"- {d['serial']}")
        return False

    def _check_connection(self):
        if not self.available:
            logger.debug("Skipping connection check: adb not available.")
            self.connected = False
            self.last_status_reason = "adb_missing"
            return False

        res = self._run_adb(['devices'])
        if res is None or res.returncode != 0:
            self.connected = False
            self.last_status_reason = "adb_command_failed"
            logger.warning("Failed to query ADB devices.")
            return False

        self.connected = self._has_usable_device(res.stdout)
        if not self.connected:
            logger.warning(f"No usable ADB device detected ({self.last_status_reason}).")
        return self.connected

    def ensure_connection(self, retries=3, retry_delay=1.0):
        for attempt in range(1, retries + 1):
            if self._check_connection():
                if attempt > 1:
                    logger.info(f"ADB device detected on attempt {attempt}/{retries}.")
                return True
            if attempt < retries:
                logger.info(f"Waiting for ADB device ({attempt}/{retries})...")
                time.sleep(retry_delay)
        return False

    def wake_screen(self):
        if not self.available or not self.connected:
            return
        res = self._run_adb(['shell', 'dumpsys', 'power'])
        if res and ("mHoldingDisplaySuspendBlocker=false" in res.stdout or "Display Power: state=OFF" in res.stdout):
            self._run_adb(['shell', 'input', 'keyevent', '26'])
            time.sleep(1)

    def is_app_running(self, package_name="com.supercell.clashofclans"):
        """Check if a given app (default: CoC) is currently running (any state)."""
        if not self.available or not self.connected:
            return False
        try:
            res = self._run_adb(['shell', 'dumpsys', 'activity', 'activities'])
            if res is None:
                return False
            if package_name in res.stdout:
                logger.debug(f"App {package_name} is running")
                return True
            logger.debug(f"App {package_name} is not running")
            return False
        except Exception as e:
            logger.debug(f"Failed to check if app is running: {e}")
            return False

    def is_app_foreground(self, package_name="com.supercell.clashofclans"):
        """Check if app is in foreground (active/focused window)."""
        if not self.available or not self.connected:
            return False
        try:
            res = self._run_adb(['shell', 'dumpsys', 'window', 'windows'])
            if res is None:
                return False
            # Look for mCurrentFocus which shows the currently focused app
            if package_name in res.stdout and "mCurrentFocus" in res.stdout:
                # More specific check: see if package appears near mCurrentFocus
                for line in res.stdout.split('\n'):
                    if 'mCurrentFocus' in line and package_name in line:
                        logger.debug(f"App {package_name} is in foreground")
                        return True
            logger.debug(f"App {package_name} is NOT in foreground")
            return False
        except Exception as e:
            logger.debug(f"Failed to check if app is foreground: {e}")
            return False

    def bring_app_to_foreground(self, package_name="com.supercell.clashofclans"):
        """Bring app to foreground if running but backgrounded."""
        if not self.available or not self.connected:
            logger.warning("Cannot bring app to foreground: no active ADB device.")
            return
        logger.info(f"Bringing {package_name} to foreground...")
        self._run_adb(['shell', 'monkey', '-p', package_name, '1'])
        time.sleep(2)
        if self.is_app_foreground(package_name):
            logger.info("App brought to foreground.")
        else:
            logger.warning("App launch command sent, but app is still not foreground.")

    def is_package_installed(self, package_name):
        if not self.available or not self.connected:
            return False
        res = self._run_adb(['shell', 'pm', 'list', 'packages', package_name])
        if res is None:
            return False
        return package_name in (res.stdout or "")

    def launch_game(self, package_name="com.supercell.clashofclans"):
        if not self.available or not self.connected:
            logger.warning("Cannot launch game: no active ADB device.")
            return False

        if not self.is_package_installed(package_name):
            logger.error("Clash of Clans is not installed on the selected emulator/device. Please install it, then run the bot again.")
            return False

        logger.info(f"Launching {package_name}...")
        # Strategy 1: monkey launcher
        self._run_adb(['shell', 'monkey', '-p', package_name, '-c', 'android.intent.category.LAUNCHER', '1'])
        time.sleep(4)
        if self.is_app_running(package_name):
            return True

        # Strategy 2: monkey direct open
        self._run_adb(['shell', 'monkey', '-p', package_name, '1'])
        time.sleep(4)
        if self.is_app_running(package_name):
            return True

        # Strategy 3: explicit launch intent
        self._run_adb(['shell', 'am', 'start', '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER', '-n', f'{package_name}/{package_name}.GameApp'])
        time.sleep(4)
        if self.is_app_running(package_name):
            return True

        logger.error("Launch attempts completed but app is still not running.")
        return False

    def get_screen(self):
        if not self.available or not self.connected:
            return None
        try:
            pipe = subprocess.Popen(
                self._adb_cmd(['exec-out', 'screencap', '-p']),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            image_bytes = pipe.stdout.read()
            if not image_bytes:
                return None
            image_array = np.frombuffer(image_bytes, dtype=np.uint8)
            screen = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            return screen
        except FileNotFoundError:
            logger.error("adb binary not found when attempting to capture screen.")
            return None

    def tap(self, x, y):
        if not self.available or not self.connected:
            logger.debug("tap skipped: no active ADB device.")
            return
        try:
            self._run_adb(['shell', 'input', 'tap', str(x), str(y)])
        except FileNotFoundError:
            logger.error("adb binary not found when attempting to tap.")

    def swipe(self, path):
        if len(path) >= 2:
            start = path[0]
            end = path[-1]
            if not self.available or not self.connected:
                logger.debug("swipe skipped: no active ADB device.")
                return
            try:
                self._run_adb(['shell', 'input', 'swipe', str(start[0]), str(start[1]), str(end[0]), str(end[1]), '300'])
            except FileNotFoundError:
                logger.error("adb binary not found when attempting to swipe.")

# By default, serial is None, which means ADB uses the only connected device.
# Change this to e.g., device = Device("emulator-5554") if you have multiple devices.
# To use the device, create an instance in your runtime entrypoint (e.g. `main.py`):
# from core.device import Device
# device = Device()


def connect_with_profile(device, profile, endpoint=None):
    device.start_adb_server()
    if profile == "custom_endpoint" and endpoint:
        device.connect_device(endpoint)
        return
    for ep in PROFILE_ENDPOINTS.get(profile, []):
        device.connect_device(ep)


def launch_emulator_for_profile(profile, logger):
    paths = PROFILE_EXECUTABLES.get(profile, [])
    for exe in paths:
        if os.path.exists(exe):
            try:
                subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                logger.info(f"Launched emulator executable: {exe}")
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


def ensure_emulator_running(profile, logger):
    if profile not in PROFILE_PROCESS_NAMES:
        return True
    if is_emulator_running(profile):
        logger.info(f"Emulator process for profile '{profile}' is already running.")
        return True
    logger.info(f"Emulator process for profile '{profile}' is not running. Launching...")
    launched = launch_emulator_for_profile(profile, logger)
    if launched:
        logger.info(f"Waiting 12 seconds for {profile} startup...")
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


def bootstrap_device(settings, save_settings, logger):
    device_cfg = settings.get("device", {})
    profile = device_cfg.get("profile", "usb_or_existing")
    endpoint = device_cfg.get("endpoint", "")
    preferred_serial = device_cfg.get("serial")
    auto_select_single = device_cfg.get("auto_select_single", True)

    device = Device(serial=preferred_serial)
    if not getattr(device, "available", False):
        logger.error("\n' adb' not found in your PATH. The bot requires adb to interact with a device.")
        logger.error("Install Android platform-tools and ensure 'adb' is on your PATH, then re-run this script.")
        logger.error("On Windows, you can download from: https://developer.android.com/studio/releases/platform-tools")
        return None

    if profile in ("ldplayer", "bluestacks", "nox", "mumu", "android_emulator"):
        ensure_emulator_running(profile, logger)

    connect_with_profile(device, profile, endpoint)
    time.sleep(0.5)

    if not device.select_device(preferred_serial=preferred_serial, auto_select_single=auto_select_single):
        logger.error("Could not resolve target device from settings.")
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
        logger.info(f"Saved selected device serial to settings: {device.serial}")

    if not device.ensure_connection(retries=3, retry_delay=1.5):
        logger.error("No usable ADB device found after retries.")
        logger.info("Falling back to setup wizard...")
        if not run_device_setup_wizard(device, settings, save_settings, logger):
            logger.error("Device setup wizard failed.")
            return None
        if not device.ensure_connection(retries=3, retry_delay=1.5):
            logger.error("Still no usable ADB device after wizard.")
            return None

    return device
