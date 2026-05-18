from .base_screen import BaseScreen
import logging
import time

logger = logging.getLogger(__name__)

class HomeScreen(BaseScreen):
    def is_current_screen(self):
        """
        Detect if we're on the home screen by checking for characteristic UI elements.
        Strict multi-anchor detection (§13.3): require all home-only anchors to
        hit. Attack! and Shop are on opposite corners and both appear only on
        the home/village screen, so a missing hit means we're on a different
        screen or occluded by a popup (recovery handles popups).
        Anchors are captured at 1600x900; the vision layer's multi-scale
        matcher handles other emulator resolutions.
        """
        anchors = [
            "home_attack_button_1600x900",
            "home_shop_button_1600x900",
        ]
        hits = 0
        for anchor in anchors:
            loc = self.ui_manager.wait_until_appears(
                anchor,
                timeout=0.6,
                use_orb_fallback=False,
                silent=True,
            )
            if loc:
                hits += 1

        if hits == len(anchors):
            logger.debug(f"Home screen detected with {hits}/{len(anchors)} strict anchors")
            return True

        logger.debug(f"Home screen not detected ({hits}/{len(anchors)} anchors)")
        return False

    def collect_resources(self):
        """Collect available resources in one screen capture.

        scan_all() takes a single screenshot and checks all three templates
        against that same frame, so the result reflects what is actually
        visible at one point in time rather than three separate captures that
        may catch different animation frames.
        """
        resources = [
            "icon_gold_mine_full",
            "icon_elixir_collector_full",
            "icon_dark_elixir_drill_full",
        ]
        # Scan up to 3 frames (0.3 s apart) so animated badges (gold mine
        # sparkle, elixir pulse) are caught at a high-confidence frame.
        # Each pass only re-scans resource types not yet detected.
        found = {}
        remaining = list(resources)
        for _ in range(3):
            if not remaining:
                break
            partial = self.ui_manager.scan_all(remaining)
            found.update(partial)
            remaining = [r for r in remaining if r not in found]
            if remaining:
                time.sleep(0.3)

        if not found:
            logger.debug("No resource badges visible.")
            return

        for name, loc in found.items():
            logger.info(f"Collecting '{name}' at {loc}")
            self.ui_manager.click(loc[0], loc[1])

        # Wait for collection animations then re-scan what we clicked.
        # Any badge still visible means the tap was dropped — click once more.
        time.sleep(0.6)
        retry = self.ui_manager.scan_all(list(found.keys()))
        for name, loc in retry.items():
            logger.info(f"Collecting '{name}' at {loc} (retry)")
            self.ui_manager.click(loc[0], loc[1])
