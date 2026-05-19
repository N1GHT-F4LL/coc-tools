import logging
from core.vision import vision

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
        for btn in ["buttons/popup/btn_close", "btn_okay", "btn_ok"]:
            if self.ui_manager.click_if_exists_quick(btn, timeout=0.2):
                closed_any = True
                logger.info(f"Closed popup button: {btn}")

        if not closed_any:
            logger.debug("No popups detected")

    def _existing_templates(self, candidates):
        existing = [name for name in candidates if name in vision.cache]
        return existing or list(candidates)

    def _wait_until_any_appears(
        self,
        candidates,
        timeout=5,
        silent=False,
        threshold=0.7,
        use_orb_fallback=True,
        validator=None,
    ):
        for template_name in self._existing_templates(candidates):
            loc = self.ui_manager.wait_until_appears(
                template_name,
                timeout=timeout,
                silent=silent,
                threshold=threshold,
                use_orb_fallback=use_orb_fallback,
            )
            if loc and (validator is None or validator(loc)):
                return loc
        return None
