import time
import os
import logging
from datetime import datetime
import cv2
from .vision import vision

logger = logging.getLogger(__name__)

class UIManager:
    def __init__(self, humanize, device):
        self.humanize = humanize
        self.device = device

    def wait_until_appears(self, template_name, timeout=5): 
        logger.info(f"Waiting for '{template_name}'...")
        start = time.time()
        while time.time() - start < timeout:
            screen = self.device.get_screen()
            if screen is None:
                # Could not obtain a screen capture; wait briefly and retry.
                time.sleep(0.5)
                continue
            loc = vision.find_template(screen, template_name)
            if loc:
                logger.info(f"Found '{template_name}' at {loc} in {time.time() - start:.1f}s")
                return loc
            time.sleep(0.5)
        logger.warning(f"Timeout waiting for '{template_name}'")
        # Save debug screenshot for post-mortem
        try:
            debug_dir = os.path.join('coc_bot', 'logs', 'debug')
            os.makedirs(debug_dir, exist_ok=True)
            last_screen = self.device.get_screen()
            if last_screen is not None:
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                out_path = os.path.join(debug_dir, f"timeout_{template_name}_{ts}.png")
                cv2.imwrite(out_path, last_screen)
                logger.info(f"Wrote debug screenshot: {out_path}")
        except Exception as e:
            logger.exception(f"Failed to write debug screenshot: {e}")
        return None

    def click(self, x, y):
        jx, jy = self.humanize.get_jittered_coords(x, y)
        logger.debug(f"Tapping {jx}, {jy}")
        self.device.tap(jx, jy)

    def click_if_exists(self, template_name):
        logger.debug(f"Checking if '{template_name}' exists...")
        loc = self.wait_until_appears(template_name, timeout=1)
        if loc:
            self.click(loc[0], loc[1])
            return True
        return False
