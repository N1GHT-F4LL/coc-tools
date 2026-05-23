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


COC_MAIN_ACTIVITY = "com.supercell.titan.GameApp"

class Device:
    def __init__(self, serial=None, strict_serial=True, adb_path=None, profile=None, endpoint=None):
        self.serial = serial
        self.strict_serial = strict_serial
        # Detect adb binary path early to avoid FileNotFoundError on subprocess.
        self.adb_path = adb_path or shutil.which("adb")
        self.available = bool(self.adb_path)
        self.connected = False
        self.last_status_reason = "unknown"
        # Stored so the transparent shell-recovery path can reconnect the
        # right endpoints after kill-server/start-server.
        self.profile = profile
        self.endpoint = endpoint
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

    def _run_adb(self, args, text=True, _recovered=False):
        if not self.available:
            return None
        try:
            res = subprocess.run(
                self._adb_cmd(args),
                capture_output=True,
                text=text,
            )
            # Auto-failover for flaky BlueStacks ADB transport.
            # If current serial shell is closed, try other ready serials.
            if (not self.strict_serial) and args and args[0] == 'shell' and self._is_shell_transport_closed(res):
                failover = self._run_shell_with_failover(args, text=text)
                if failover is not None:
                    return failover
            # Transparent transport recovery: shell-closed is a known BlueStacks
            # quirk that survives across calls until the adb server is restarted.
            # Try once per command to kick the transport and retry.
            if (not _recovered) and args and args[0] == 'shell' and self._is_shell_transport_closed(res):
                logger.warning("ADB shell transport closed. Attempting recovery (kill-server/start-server)...")
                if self.try_recover_adb_transport(profile=self.profile, endpoint=self.endpoint):
                    return self._run_adb(args, text=text, _recovered=True)
            return res
        except FileNotFoundError:
            self.connected = False
            self.last_status_reason = "adb_missing"
            return None

    def _is_shell_transport_closed(self, res):
        if res is None:
            return False
        msg = ((res.stdout or "") + " " + (res.stderr or "")).lower()
        return "error: closed" in msg or "device not found" in msg

    def _list_ready_serials_raw(self):
        """
        Read ready device serials directly from `adb devices` without using self.serial.
        """
        if not self.available:
            return []
        try:
            res = subprocess.run([self.adb_path, 'devices'], capture_output=True, text=True)
        except Exception:
            return []
        if res.returncode != 0:
            return []
        serials = []
        for line in (res.stdout or "").splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                serials.append(parts[0])
        return serials

    def shell_health_check(self, serial=None):
        """
        Check whether adb shell is usable for a serial.
        """
        if not self.available:
            return False
        target = serial or self.serial
        if not target:
            return False
        for _ in range(3):
            try:
                res = subprocess.run(
                    [self.adb_path, "-s", target, "shell", "id"],
                    capture_output=True,
                    text=True,
                )
            except Exception:
                continue
            if res.returncode != 0:
                time.sleep(0.2)
                continue
            out = ((res.stdout or "") + " " + (res.stderr or "")).lower()
            if "uid=" in out and "error: closed" not in out:
                return True
            time.sleep(0.2)
        return False

    def pick_healthy_serial(self, preferred_serial=None):
        """
        Choose the best serial by shell health.
        """
        ready = self._list_ready_serials_raw()
        if not ready:
            return None

        # Prefer configured serial if its shell is healthy.
        if preferred_serial and preferred_serial in ready and self.shell_health_check(preferred_serial):
            return preferred_serial

        # Otherwise pick first healthy serial.
        for serial in ready:
            if self.shell_health_check(serial):
                return serial
        return None

    def try_recover_adb_transport(self, profile=None, endpoint=None):
        """
        Best-effort transport recovery for flaky emulator ADB shell.
        """
        if not self.available:
            return False
        try:
            subprocess.run([self.adb_path, "kill-server"], capture_output=True, text=True)
            subprocess.run([self.adb_path, "start-server"], capture_output=True, text=True)
            if endpoint:
                subprocess.run([self.adb_path, "connect", endpoint], capture_output=True, text=True)
            if profile and profile in PROFILE_ENDPOINTS:
                for ep in PROFILE_ENDPOINTS.get(profile, []):
                    subprocess.run([self.adb_path, "connect", ep], capture_output=True, text=True)
        except Exception:
            return False
        time.sleep(0.5)
        return True

    def _run_shell_with_failover(self, shell_args, text=True):
        """
        Try shell command on alternative ready serials when current serial transport is closed.
        """
        candidates = self._list_ready_serials_raw()
        if not candidates:
            return None

        current = self.serial
        for serial in candidates:
            if serial == current:
                continue
            try:
                cmd = [self.adb_path, '-s', serial] + shell_args
                res = subprocess.run(cmd, capture_output=True, text=text)
            except Exception:
                continue
            if res.returncode == 0 and not self._is_shell_transport_closed(res):
                self.serial = serial
                logger.warning(f"ADB shell transport on '{current}' was closed. Switched to '{serial}'.")
                return res
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

    def find_serial_with_package(self, package_name):
        """
        Try all ready ADB devices and return first serial where package is installed.
        Returns None if not found or package state cannot be verified.
        """
        devices = self.list_devices()
        ready = [d["serial"] for d in devices if d.get("state") == "device"]
        original_serial = self.serial
        try:
            for serial in ready:
                self.serial = serial
                state = self.is_package_installed(package_name)
                if state is True:
                    return serial
        finally:
            self.serial = original_serial
        return None

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
                    logger.debug(f"ADB device detected on attempt {attempt}/{retries}.")
                return True
            if attempt < retries:
                logger.debug(f"Waiting for ADB device ({attempt}/{retries})...")
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
        """Check if app has an active process or is in foreground."""
        if not self.available or not self.connected:
            return False
        try:
            # Fast path: app is foreground.
            if self.is_app_foreground(package_name):
                return True

            # Process check (more reliable than broad dumpsys activity parsing).
            res_pid = self._run_adb(['shell', 'pidof', package_name])
            if res_pid and (res_pid.stdout or "").strip():
                return True

            # Fallback for devices where pidof is unavailable.
            res_ps = self._run_adb(['shell', 'ps'])
            if res_ps and package_name in (res_ps.stdout or ""):
                return True

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

    def resolve_launch_component(self, package_name):
        """
        Resolve best launcher component for a package.
        Returns component string: <package>/<activity> or None.
        """
        if not self.available or not self.connected:
            return None

        # Preferred: package manager resolver.
        res = self._run_adb(['shell', 'cmd', 'package', 'resolve-activity', '--brief', package_name])
        if res is not None and res.returncode == 0:
            for line in reversed((res.stdout or "").splitlines()):
                line = line.strip()
                if line.startswith(package_name + "/"):
                    return line

        # Fallback for environments where cmd package is unreliable.
        return f"{package_name}/{COC_MAIN_ACTIVITY}"

    def bring_app_to_foreground(self, package_name="com.supercell.clashofclans"):
        """Bring app to foreground if running but backgrounded."""
        if not self.available or not self.connected:
            logger.warning("Cannot bring app to foreground: no active ADB device.")
            return False

        logger.info(f"Bringing {package_name} to foreground...")
        component = self.resolve_launch_component(package_name)

        # Strategy 0: explicit known launcher activity (most reliable for CoC).
        if component:
            self._run_adb(['shell', 'am', 'start', '-n', component])
            time.sleep(2)
            if self.is_app_foreground(package_name):
                return True

        # Strategy 1: monkey quick launch
        self._run_adb(['shell', 'monkey', '-p', package_name, '1'])
        time.sleep(2)
        if self.is_app_foreground(package_name):
            return True

        # Strategy 2: launcher intent
        if component:
            self._run_adb(['shell', 'am', 'start', '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER', '-n', component])
        else:
            self._run_adb(['shell', 'am', 'start', '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER', '-p', package_name])
        time.sleep(2)
        if self.is_app_foreground(package_name):
            return True

        logger.warning("Could not bring app to foreground.")
        return False

    def get_screen_size(self):
        """Return (width, height) reported by `wm size`. Prefers override over physical."""
        if not self.available or not self.connected:
            return None
        res = self._run_adb(['shell', 'wm', 'size'])
        if res is None or res.returncode != 0:
            return None
        text = res.stdout or ""
        # Override line takes precedence over Physical when both are present.
        for prefix in ("Override size:", "Physical size:"):
            for line in text.splitlines():
                line = line.strip()
                if line.startswith(prefix):
                    try:
                        wh = line.split(":", 1)[1].strip().lower()
                        w, h = wh.split("x")
                        return (int(w), int(h))
                    except Exception:
                        return None
        return None

    def get_screen_density(self):
        """Return DPI reported by `wm density`. Prefers override over physical."""
        if not self.available or not self.connected:
            return None
        res = self._run_adb(['shell', 'wm', 'density'])
        if res is None or res.returncode != 0:
            return None
        text = res.stdout or ""
        for prefix in ("Override density:", "Physical density:"):
            for line in text.splitlines():
                line = line.strip()
                if line.startswith(prefix):
                    try:
                        return int(line.split(":", 1)[1].strip())
                    except Exception:
                        return None
        return None

    def enforce_resolution(self, target_resolution, target_density=None, package_name="com.supercell.clashofclans"):
        """
        Lock the device to a known display geometry via `wm size` / `wm density`.

        If the target app is running and size needs to change, force-stop it
        first so its relaunch picks up the new layout cleanly (CoC does not
        re-layout robustly on live resolution change).

        target_resolution: "WIDTHxHEIGHT" string, e.g. "1600x900".
        target_density: integer DPI, or None to leave density untouched.
        Returns True when the target size is in effect afterwards.
        """
        if not self.available or not self.connected:
            return False
        try:
            tw_str, th_str = target_resolution.lower().split("x")
            tw, th = int(tw_str), int(th_str)
        except Exception:
            logger.error(f"Invalid target_resolution '{target_resolution}'. Use WIDTHxHEIGHT (e.g. 1600x900).")
            return False

        current_size = self.get_screen_size()
        current_density = self.get_screen_density()
        size_needs_change = current_size != (tw, th)
        density_needs_change = target_density is not None and current_density != target_density

        if not (size_needs_change or density_needs_change):
            logger.debug(f"Display already at {tw}x{th} @ density {current_density}.")
            return True

        logger.info(
            f"Enforcing display: size {current_size} -> {tw}x{th}, density {current_density} -> {target_density}"
        )

        if size_needs_change and self.is_app_running(package_name):
            logger.warning(f"{package_name} is running; force-stopping before resolution change.")
            self._run_adb(['shell', 'am', 'force-stop', package_name])
            time.sleep(1.0)

        if size_needs_change:
            res = self._run_adb(['shell', 'wm', 'size', f"{tw}x{th}"])
            if res is None or res.returncode != 0:
                logger.warning(f"Failed to set wm size to {tw}x{th}.")
                return False

        if density_needs_change:
            res = self._run_adb(['shell', 'wm', 'density', str(target_density)])
            if res is None or res.returncode != 0:
                logger.warning(f"Failed to set wm density to {target_density}; continuing with size change only.")

        time.sleep(0.5)
        actual = self.get_screen_size()
        if actual != (tw, th):
            logger.warning(f"After wm size, screen is {actual} (expected {tw}x{th}).")
            return False
        logger.info(
            f"Display locked to {tw}x{th}" + (f" @ density {target_density}" if target_density else "")
        )
        return True

    def is_package_installed(self, package_name):
        if not self.available or not self.connected:
            return None
        # Primary check.
        res = self._run_adb(['shell', 'pm', 'list', 'packages', package_name])
        if res is not None and res.returncode == 0 and package_name in (res.stdout or ""):
            return True

        # Fallback: some BlueStacks builds intermittently close pm shell command.
        res_ds = self._run_adb(['shell', 'dumpsys', 'package', package_name])
        if res_ds is None:
            self.last_status_reason = "package_check_unavailable"
            return None
        if res_ds.returncode != 0:
            if self._is_shell_transport_closed(res) or self._is_shell_transport_closed(res_ds):
                self.last_status_reason = "adb_shell_closed"
                return None
            return False
        out = res_ds.stdout or ""
        return f"Package [{package_name}]" in out or f"package={package_name}" in out

    def launch_game(self, package_name="com.supercell.clashofclans"):
        if not self.available or not self.connected:
            logger.warning("Cannot launch game: no active ADB device.")
            return False

        install_state = self.is_package_installed(package_name)
        if install_state is None:
            logger.error("Cannot verify app installation due to unstable ADB shell connection (error: closed).")
            logger.error("Please restart BlueStacks and ADB, then run the bot again.")
            return False
        if not install_state:
            logger.error("Clash of Clans is not installed on the selected emulator/device. Please install it, then run the bot again.")
            return False

        logger.info(f"Launching {package_name}...")
        component = self.resolve_launch_component(package_name)

        # Strategy 0: explicit known activity
        if component:
            self._run_adb(['shell', 'am', 'start', '-n', component])
            time.sleep(4)
            if self.is_app_running(package_name):
                return True

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
        if component:
            self._run_adb(['shell', 'am', 'start', '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER', '-n', component])
        else:
            self._run_adb(['shell', 'am', 'start', '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER', '-p', package_name])
        time.sleep(4)
        if self.is_app_running(package_name):
            return True

        logger.error("Launch attempts completed but app is still not running.")
        return False

    def restart_game(self, package_name="com.supercell.clashofclans"):
        """
        Force-stop the app and relaunch it. Used as a recovery path when the
        bot is stuck on a non-recognized state (e.g. inactivity disconnect
        popup) and `close_popups` cannot escape it. Returns True when the app
        is running afterwards.
        """
        if not self.available or not self.connected:
            logger.warning("Cannot restart game: no active ADB device.")
            return False
        logger.info(f"Restarting {package_name} (force-stop + launch)...")
        self._run_adb(['shell', 'am', 'force-stop', package_name])
        time.sleep(1.5)
        return self.launch_game(package_name)

    def ensure_coc_ready(self, package_name, settings, save_settings, logger):
        """
        Ensure CoC is installed, launched, and foregrounded.
        Returns True when ready, False otherwise.
        """
        install_state = self.is_package_installed(package_name)
        if install_state is None:
            logger.error("Cannot verify Clash of Clans installation because ADB shell connection is unstable.")
            logger.error("Action: restart BlueStacks, then run `adb kill-server`, `adb start-server`, and run the bot again.")
            return False

        if not install_state:
            alt_serial = self.find_serial_with_package(package_name)
            if alt_serial and alt_serial != self.serial:
                logger.warning(f"CoC not found on current serial. Switching to: {alt_serial}")
                self.serial = alt_serial
                settings.setdefault("device", {})
                settings["device"]["serial"] = alt_serial
                save_settings(settings)
                install_state = self.is_package_installed(package_name)

            if not install_state:
                logger.error("Clash of Clans is not installed on the selected emulator/device. Please install it, then run the bot again.")
                return False

        if self.is_app_running(package_name):
            logger.info("CoC is running.")
            if not self.is_app_foreground(package_name):
                logger.warning("CoC is running but in background. Bringing to foreground...")
                if not self.bring_app_to_foreground(package_name):
                    logger.error("CoC is running but cannot be brought to foreground. Stop bot.")
                    return False
            return True

        logger.warning("CoC is not running. Launching game...")
        if self.launch_game(package_name):
            return True

        alt_serial = self.find_serial_with_package(package_name)
        if alt_serial and alt_serial != self.serial:
            logger.warning(f"Launch failed on current serial. Trying fallback serial: {alt_serial}")
            self.serial = alt_serial
            settings.setdefault("device", {})
            settings["device"]["serial"] = alt_serial
            save_settings(settings)
            return self.launch_game(package_name)
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

    def _pixel_to_event(self, px, py, max_x_evt, max_y_evt, sw, sh):
        ex = max(0, min(max_x_evt, int(px * max_x_evt / sw)))
        ey = max(0, min(max_y_evt, int(py * max_y_evt / sh)))
        return ex, ey

    def _find_touch_input_device(self):
        """
        Find the multi-touch event device (e.g. /dev/input/event4 on BlueStacks).
        Returns (path, max_x, max_y) or (None, None, None).
        Looks for a device exposing ABS_MT_POSITION_X.
        """
        if not self.available or not self.connected:
            return (None, None, None)
        res = self._run_adb(['shell', 'getevent', '-pl'])
        if res is None or res.returncode != 0:
            return (None, None, None)
        current_path = None
        current_has_mt_x = False
        current_max_x = None
        current_max_y = None
        for line in (res.stdout or "").splitlines():
            stripped = line.strip()
            if stripped.startswith("add device"):
                # Flush previous if it was MT-capable
                if current_path and current_has_mt_x:
                    return (current_path, current_max_x, current_max_y)
                # Start new device block
                parts = stripped.split(":", 1)
                current_path = parts[1].strip() if len(parts) > 1 else None
                current_has_mt_x = False
                current_max_x = None
                current_max_y = None
            elif "ABS_MT_POSITION_X" in stripped:
                current_has_mt_x = True
                # Parse max from "ABS_MT_POSITION_X     : value 0, min 0, max 32767, ..."
                try:
                    current_max_x = int(stripped.split("max")[1].split(",")[0].strip())
                except Exception:
                    current_max_x = None
            elif "ABS_MT_POSITION_Y" in stripped:
                try:
                    current_max_y = int(stripped.split("max")[1].split(",")[0].strip())
                except Exception:
                    current_max_y = None
        if current_path and current_has_mt_x:
            return (current_path, current_max_x, current_max_y)
        return (None, None, None)

    def pinch(self, direction='out', center=None, span_pixels=400, steps=15, repeats=1):
        """
        Multi-touch pinch via sendevent (Protocol A: two fingers separated by
        SYN_MT_REPORT, frames separated by SYN_REPORT). Used to zoom the CoC
        village in/out so collectors at the edges become visible.

        direction:    'out' fingers move toward center (zoom out),
                      'in'  fingers move apart from center (zoom in)
        center:       (x, y) pixel center; defaults to screen midpoint
        span_pixels:  far-finger distance from center (closer end = 1/4 of this)
        steps:        number of interpolated frames
        repeats:      consecutive pinches (each lifts fingers between). Useful
                      because CoC clamps zoom-out at a max level, so a few
                      repeats reliably hits the floor regardless of starting zoom.
        Returns True on success.
        """
        if not self.available or not self.connected:
            return False

        event_dev, max_x_evt, max_y_evt = self._find_touch_input_device()
        if not event_dev:
            logger.warning("No multi-touch input device found; cannot pinch.")
            return False

        size = self.get_screen_size()
        if not size:
            logger.warning("Cannot pinch: failed to read screen size.")
            return False
        sw, sh = size
        cx, cy = center or (sw // 2, sh // 2)

        # BlueStacks Virtual Touch and most MT devices use a normalized 0..max
        # coordinate space rather than raw pixels. Map accordingly.
        max_x_evt = max_x_evt or sw
        max_y_evt = max_y_evt or sh

        if direction == 'out':
            start_d, end_d = span_pixels, max(20, span_pixels // 5)
        else:
            start_d, end_d = max(20, span_pixels // 5), span_pixels

        EV_ABS = 3
        EV_SYN = 0
        ABS_MT_POSITION_X = 0x35
        ABS_MT_POSITION_Y = 0x36
        SYN_REPORT = 0
        SYN_MT_REPORT = 2

        def build_script():
            cmds = []
            def se(t, c, v):
                cmds.append(f"sendevent {event_dev} {t} {c} {v}")
            for i in range(steps + 1):
                t = i / max(1, steps)
                d = int(start_d + (end_d - start_d) * t)
                x1, y1 = self._pixel_to_event(cx - d, cy, max_x_evt, max_y_evt, sw, sh)
                x2, y2 = self._pixel_to_event(cx + d, cy, max_x_evt, max_y_evt, sw, sh)
                se(EV_ABS, ABS_MT_POSITION_X, x1)
                se(EV_ABS, ABS_MT_POSITION_Y, y1)
                se(EV_SYN, SYN_MT_REPORT, 0)
                se(EV_ABS, ABS_MT_POSITION_X, x2)
                se(EV_ABS, ABS_MT_POSITION_Y, y2)
                se(EV_SYN, SYN_MT_REPORT, 0)
                se(EV_SYN, SYN_REPORT, 0)
                cmds.append("sleep 0.04")
            # Lift all fingers: empty frame (no MT reports before SYN).
            se(EV_SYN, SYN_REPORT, 0)
            return ";".join(cmds)

        logger.info(
            f"Pinch {direction} x{repeats}: device={event_dev} center=({cx},{cy}) "
            f"span={start_d}->{end_d} steps={steps}"
        )
        script = build_script()
        for r in range(repeats):
            res = self._run_adb(['shell', script])
            if res is None or res.returncode != 0:
                logger.warning(f"Pinch sendevent script returned non-zero on repeat {r + 1}.")
                return False
            if r < repeats - 1:
                # Let CoC settle so the next pinch starts from a stable camera.
                time.sleep(0.3)
        return True

    def _curved_swipe(self, path, duration_ms=300):
        if not self.available or not self.connected:
            return False
        event_dev, max_x_evt, max_y_evt = self._find_touch_input_device()
        if not event_dev:
            return False
        size = self.get_screen_size()
        if not size:
            return False
        sw, sh = size
        max_x_evt = max_x_evt or sw
        max_y_evt = max_y_evt or sh

        EV_ABS, EV_SYN = 3, 0
        ABS_MT_POSITION_X, ABS_MT_POSITION_Y = 0x35, 0x36
        SYN_REPORT, SYN_MT_REPORT = 0, 2

        sleep_per = max(0.016, duration_ms / 1000 / max(1, len(path) - 1))
        cmds = []
        def se(t, c, v): cmds.append(f"sendevent {event_dev} {t} {c} {v}")

        for px, py in path:
            ex, ey = self._pixel_to_event(px, py, max_x_evt, max_y_evt, sw, sh)
            se(EV_ABS, ABS_MT_POSITION_X, ex)
            se(EV_ABS, ABS_MT_POSITION_Y, ey)
            se(EV_SYN, SYN_MT_REPORT, 0)
            se(EV_SYN, SYN_REPORT, 0)
            cmds.append(f"sleep {sleep_per:.3f}")
        se(EV_SYN, SYN_REPORT, 0)

        script = ";".join(cmds)
        res = self._run_adb(['shell', script])
        return res is not None and res.returncode == 0

    def tap(self, x, y):
        if not self.available or not self.connected:
            logger.debug("tap skipped: no active ADB device.")
            return
        try:
            self._run_adb(['shell', 'input', 'tap', str(x), str(y)])
        except FileNotFoundError:
            logger.error("adb binary not found when attempting to tap.")

    def swipe(self, path):
        if len(path) < 2:
            return
        if len(path) > 2 and self._curved_swipe(path):
            return
        start, end = path[0], path[-1]
        if not self.available or not self.connected:
            logger.debug("swipe skipped: no active ADB device.")
            return
        try:
            self._run_adb(['shell', 'input', 'swipe',
                           str(start[0]), str(start[1]),
                           str(end[0]), str(end[1]), '300'])
        except FileNotFoundError:
            logger.error("adb binary not found when attempting to swipe.")

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

    # Choose a shell-healthy serial to avoid BlueStacks dual-endpoint instability.
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

    # Lock the display geometry before any vision work so the asset cache (which
    # is tied to a capture resolution) lines up with what we actually screenshot.
    if device_cfg.get("enforce_resolution"):
        target_res = device_cfg.get("target_resolution")
        target_density = device_cfg.get("target_density")
        if target_res:
            device.enforce_resolution(target_res, target_density)
        else:
            logger.warning("enforce_resolution is true but device.target_resolution is unset; skipping.")

    return device
