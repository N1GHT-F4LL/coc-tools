import logging

logger = logging.getLogger(__name__)

class BaseScreen:
    def __init__(self, ui_manager):
        self.ui_manager = ui_manager

    def is_current_screen(self):
        raise NotImplementedError

    def close_popups(self):
        """Quickly attempt to close any visible popups (close/okay buttons) with minimal wait."""
        logger.debug("Quick scan for popups...")
        closed_any = False
        
        # Try to close generic close/okay buttons with very short timeout (0.3s each)
        for btn in ["ui/btn_close", "btn_okay", "btn_ok"]:
            if self.ui_manager.click_if_exists_quick(btn, timeout=0.2):
                closed_any = True
                logger.info(f"Closed popup button: {btn}")
        
        if not closed_any:
            logger.debug("No popups detected")
