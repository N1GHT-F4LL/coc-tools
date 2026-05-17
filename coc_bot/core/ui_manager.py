import time
from .vision import vision

class UIManager:
    def __init__(self, humanize, device):
        self.humanize = humanize
        self.device = device

    def wait_until_appears(self, template_name, timeout=5): 
        print(f"Waiting for '{template_name}'...")
        start = time.time()
        while time.time() - start < timeout:
            screen = self.device.get_screen()
            if screen is None:
                # Could not obtain a screen capture; wait briefly and retry.
                time.sleep(0.5)
                continue
            loc = vision.find_template(screen, template_name)
            if loc:
                print(f"Found '{template_name}' at {loc} in {time.time() - start:.1f}s")
                return loc
            time.sleep(0.5)
        print(f"Timeout waiting for '{template_name}'")
        return None

    def click(self, x, y):
        jx, jy = self.humanize.get_jittered_coords(x, y)
        print(f"Tapping {jx}, {jy}")
        self.device.tap(jx, jy)

    def click_if_exists(self, template_name):
        print(f"Checking if '{template_name}' exists...")
        loc = self.wait_until_appears(template_name, timeout=1)
        if loc:
            self.click(loc[0], loc[1])
            return True
        return False
