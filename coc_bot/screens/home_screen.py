from .base_screen import BaseScreen
import logging

logger = logging.getLogger(__name__)

class HomeScreen(BaseScreen):
    def is_current_screen(self):
        """Strict two-anchor detection (§13.3): both must hit in one frame.

        Attack! and Shop are on opposite corners — both visible only on the
        village screen. ORB fallback off to prevent false positives on the
        emulator launcher or in-game store.
        """
        anchors = [
            "buttons/home/btn_attack",
            "buttons/home/btn_shop",
        ]
        found = self.ui_manager.scan_all(anchors, use_orb_fallback=False)
        detected = len(found) == len(anchors)
        logger.debug(
            f"Home screen {'detected' if detected else 'not detected'} "
            f"({len(found)}/{len(anchors)} anchors)"
        )
        return detected

    def collect_resources(self):
        """Detect and collect all currently full resource collectors."""
        resources = [
            "buildings/resource_collectors/icon_gold_mine_full",
            "buildings/resource_collectors/icon_elixir_collector_full",
            "buildings/resource_collectors/icon_dark_elixir_drill_full",
        ]
        # Try up to 3 frames 0.3 s apart: animated badges (sparkle, pulse) may
        # score below threshold mid-animation but pass on the next frame.
        found = {}
        remaining = list(resources)
        for _ in range(3):
            if not remaining:
                break
            found.update(self.ui_manager.scan_all(remaining))
            remaining = [r for r in remaining if r not in found]
            if remaining:
                self.ui_manager._poll_sleep(0.3)

        if not found:
            logger.debug("No resource badges visible.")
            return

        for name, loc in found.items():
            logger.info(f"Collecting '{name}' at {loc}")
            self.ui_manager.click(loc[0], loc[1])

        # Re-scan after animations clear; a badge still visible means the
        # ADB tap was dropped — click it once more.
        self.ui_manager._poll_sleep(0.6)
        for name, loc in self.ui_manager.scan_all(found).items():
            logger.debug(f"Collecting '{name}' at {loc} (retry)")
            self.ui_manager.click(loc[0], loc[1])
