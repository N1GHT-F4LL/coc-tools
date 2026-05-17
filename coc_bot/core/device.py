import subprocess
import cv2
import numpy as np
import time
import shutil
import sys
import logging

logger = logging.getLogger(__name__)

class Device:
    def __init__(self, serial=None):
        self.serial = serial
        # Detect adb binary path early to avoid FileNotFoundError on subprocess.
        self.adb_path = shutil.which("adb")
        self.available = bool(self.adb_path)
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

    def _check_connection(self):
        if not self.available:
            logger.debug("Skipping connection check: adb not available.")
            return
        try:
            res = subprocess.run(self._adb_cmd(['devices']), capture_output=True, text=True)
            if "device\n" not in res.stdout:
                logger.warning("No ADB devices found or unauthorized.")
        except FileNotFoundError:
            print("[Device] ERROR: adb binary missing when checking devices.")

    def wake_screen(self):
        if not self.available:
            return
        try:
            res = subprocess.run(self._adb_cmd(['shell', 'dumpsys', 'power']), capture_output=True, text=True)
            if "mHoldingDisplaySuspendBlocker=false" in res.stdout or "Display Power: state=OFF" in res.stdout:
                subprocess.run(self._adb_cmd(['shell', 'input', 'keyevent', '26']))
                time.sleep(1)
        except FileNotFoundError:
            logger.error("adb binary not found when attempting to wake screen.")

    def launch_game(self):
        if not self.available:
            logger.warning("Cannot launch game: adb not available.")
            return
        package_name = "com.supercell.clashofclans"
        subprocess.run(self._adb_cmd(['shell', 'monkey', '-p', package_name, '-c', 'android.intent.category.LAUNCHER', '1']), capture_output=True)
        time.sleep(5)

    def get_screen(self):
        if not self.available:
            return None
        try:
            pipe = subprocess.Popen(self._adb_cmd(['exec-out', 'screencap', '-p']), stdout=subprocess.PIPE)
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
        if not self.available:
            logger.debug("tap skipped: adb not available.")
            return
        try:
            subprocess.run(self._adb_cmd(['shell', 'input', 'tap', str(x), str(y)]))
        except FileNotFoundError:
            logger.error("adb binary not found when attempting to tap.")

    def swipe(self, path):
        if len(path) >= 2:
            start = path[0]
            end = path[-1]
            if not self.available:
                logger.debug("swipe skipped: adb not available.")
                return
            try:
                subprocess.run(self._adb_cmd(['shell', 'input', 'swipe', str(start[0]), str(start[1]), str(end[0]), str(end[1]), '300']))
            except FileNotFoundError:
                logger.error("adb binary not found when attempting to swipe.")

# By default, serial is None, which means ADB uses the only connected device.
# Change this to e.g., device = Device("emulator-5554") if you have multiple devices.
# To use the device, create an instance in your runtime entrypoint (e.g. `main.py`):
# from core.device import Device
# device = Device()
