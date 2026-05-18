from .base_screen import BaseScreen
import logging

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
        """Collect resources from gold mine, elixir collector, dark elixir drill."""
        logger.info("Collecting resources...")
        # Tìm và click mỏ vàng/elixir
        self.ui_manager.click_if_exists("icon_gold_mine_full")
        self.ui_manager.click_if_exists("icon_elixir_collector_full")
        self.ui_manager.click_if_exists("icon_dark_elixir_drill_full")
