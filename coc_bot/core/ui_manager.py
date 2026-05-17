import time
from .device import device
from .vision import vision

class UIManager:
    def __init__(self, humanize):
        self.humanize = humanize

    def wait_until_appears(self, template_name, timeout=5): 
        print(f"Waiting for '{template_name}'...")
        start = time.time()
        while time.time() - start < timeout:
            screen = device.get_screen()
            # Note: threshold is ignored in ORB, but we keep signature for now
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
        device.tap(jx, jy)

    def click_if_exists(self, template_name):
        print(f"Checking if '{template_name}' exists...")
        loc = self.wait_until_appears(template_name, timeout=1)
        if loc:
            self.click(loc[0], loc[1])
            return True
        return False
