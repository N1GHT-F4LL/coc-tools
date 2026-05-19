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

    def wait_until_appears(self, template_name, timeout=5, silent=False, use_orb_fallback=True, threshold=0.7):
        """Poll until template appears or timeout expires; returns (cx, cy) or None."""
        if not silent:
            logger.info(f"Waiting for '{template_name}'...")
        else:
            logger.debug(f"Waiting for '{template_name}'...")

        start = time.time()
        screen = None
        while time.time() - start < timeout:
            screen = self.device.get_screen()
            if screen is None:
                time.sleep(0.5)
                continue
            loc = vision.find_template(
                screen,
                template_name,
                threshold=threshold,
                use_orb_fallback=use_orb_fallback,
            )
            if loc:
                logger.debug(f"Found '{template_name}' at {loc} in {time.time() - start:.1f}s")
                return loc
            time.sleep(0.5)

        if not silent:
            logger.warning(f"Timeout waiting for '{template_name}'")
        else:
            logger.debug(f"Timeout waiting for '{template_name}'")

        # Reuse the last captured frame — no extra screencap needed.
        try:
            if screen is not None:
                debug_dir = os.path.join('coc_bot', 'logs', 'debug')
                os.makedirs(debug_dir, exist_ok=True)
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                out_path = os.path.join(debug_dir, f"timeout_{template_name}_{ts}.png")
                cv2.imwrite(out_path, screen)
                logger.debug(f"Wrote debug screenshot: {out_path}")
        except Exception as e:
            logger.exception(f"Failed to write debug screenshot: {e}")
        return None

    def click(self, x, y):
        jx, jy = self.humanize.get_jittered_coords(x, y)
        logger.debug(f"Tapping {jx}, {jy}")
        self.device.tap(jx, jy)

    def click_if_exists_quick(self, template_name, timeout=0.3):
        """Quick click if element exists (for popup scanning with minimal wait)."""
        logger.debug(f"Quick checking if '{template_name}' exists...")
        loc = self.wait_until_appears(template_name, timeout=timeout, silent=True)
        if loc:
            self.click(loc[0], loc[1])
            return True
        return False

    def click_if_exists(self, template_name):
        """Check if element exists and click it."""
        logger.debug(f"Checking if '{template_name}' exists...")
        loc = self.wait_until_appears(template_name, timeout=1)
        if loc:
            self.click(loc[0], loc[1])
            return True
        return False

    def scan_all(self, template_names, use_orb_fallback=False):
        """Capture the screen once and find one instance of each template.

        Returns {name: (x, y)} for every template that matched. All templates
        are checked against the same single screenshot so the result reflects
        one consistent point in time.
        """
        screen = self.device.get_screen()
        if screen is None:
            return {}
        found = {}
        for name in template_names:
            loc = vision.find_template(screen, name, use_orb_fallback=use_orb_fallback)
            if loc:
                found[name] = loc
        return found
