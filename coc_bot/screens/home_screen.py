from .base_screen import BaseScreen
import logging

logger = logging.getLogger(__name__)

class HomeScreen(BaseScreen):
    def is_current_screen(self):
        """
        Detect if we're on the home screen by checking for characteristic UI elements.
        Home screen typically has Attack button and resource displays.
        """
        # Try multiple anchor images to detect home screen
        anchors = ["icon_attack", "btn_attack", "attack"]
        
        for anchor in anchors:
            loc = self.ui_manager.wait_until_appears(anchor, timeout=1)
            if loc:
                logger.debug(f"Home screen detected via {anchor} at {loc}")
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
