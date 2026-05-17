import subprocess
import cv2
import numpy as np
import time

class Device:
    def __init__(self, serial=None):
        self.serial = serial
        self._check_connection()
        self.wake_screen()
        # self.launch_game() # Commented out so it doesn't interrupt your current screen

    def _adb_cmd(self, args):
        cmd = ['adb']
        if self.serial:
            cmd.extend(['-s', self.serial])
        cmd.extend(args)
        return cmd

    def _check_connection(self):
        res = subprocess.run(['adb', 'devices'], capture_output=True, text=True)
        if "device\n" not in res.stdout:
            print("[Device] WARNING: No ADB devices found or unauthorized.")

    def wake_screen(self):
        res = subprocess.run(self._adb_cmd(['shell', 'dumpsys', 'power']), capture_output=True, text=True)
        if "mHoldingDisplaySuspendBlocker=false" in res.stdout or "Display Power: state=OFF" in res.stdout:
            subprocess.run(self._adb_cmd(['shell', 'input', 'keyevent', '26']))
            time.sleep(1)

    def launch_game(self):
        package_name = "com.supercell.clashofclans"
        subprocess.run(self._adb_cmd(['shell', 'monkey', '-p', package_name, '-c', 'android.intent.category.LAUNCHER', '1']), capture_output=True)
        time.sleep(5)

    def get_screen(self):
        pipe = subprocess.Popen(self._adb_cmd(['exec-out', 'screencap', '-p']), stdout=subprocess.PIPE)
        image_bytes = pipe.stdout.read()
        if not image_bytes:
            return None
        image_array = np.frombuffer(image_bytes, dtype=np.uint8)
        screen = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        return screen

    def tap(self, x, y):
        subprocess.run(self._adb_cmd(['shell', 'input', 'tap', str(x), str(y)]))

    def swipe(self, path):
        if len(path) >= 2:
            start = path[0]
            end = path[-1]
            subprocess.run(self._adb_cmd(['shell', 'input', 'swipe', str(start[0]), str(start[1]), str(end[0]), str(end[1]), '300']))

# By default, serial is None, which means ADB uses the only connected device.
# Change this to e.g., device = Device("emulator-5554") if you have multiple devices.
device = Device()
