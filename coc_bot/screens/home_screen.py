from .base_screen import BaseScreen
import logging

logger = logging.getLogger(__name__)

class HomeScreen(BaseScreen):
    def is_current_screen(self):
        """
        Detect if we're on the home screen by checking for characteristic UI elements.
        Home screen typically has Attack button and resource displays.
        """
        anchors = ["icon_attack", "btn_attack", "attack"]
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

        if hits >= 2:
            logger.debug(f"Home screen detected with {hits} strict anchors")
            return True

        logger.debug("Home screen not detected")
        return False

    def collect_resources(self):
        """Collect resources from gold mine, elixir collector, dark elixir drill."""
        logger.info("Collecting resources...")
        # Tìm và click mỏ vàng/elixir
        self.ui_manager.click_if_exists("icon_gold_mine_full")
        self.ui_manager.click_if_exists("icon_elixir_collector_full")
        self.ui_manager.click_if_exists("icon_dark_elixir_drill_full")
