import logging
import time
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
        templates = self._existing_templates(candidates)
        if not templates:
            return None

        # Single template: delegate to wait_until_appears (writes debug screenshot on timeout).
        if len(templates) == 1:
            loc = self.ui_manager.wait_until_appears(
                templates[0],
                timeout=timeout,
                silent=silent,
                threshold=threshold,
                use_orb_fallback=use_orb_fallback,
            )
            return loc if (loc and (validator is None or validator(loc))) else None

        # Multiple templates: check all per frame within a shared deadline.
        # The old sequential approach gave each template the full timeout, multiplying
        # the worst-case wait by the number of templates (e.g. 360 s instead of 180 s).
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.ui_manager._stopped():
                return None
            found = self.ui_manager.scan_all(
                templates, use_orb_fallback=use_orb_fallback, threshold=threshold
            )
            for name in templates:
                loc = found.get(name)
                if loc and (validator is None or validator(loc)):
                    return loc
            self.ui_manager._poll_sleep(0.5)

        if not silent:
            logger.warning(f"Timeout waiting for any of: {templates}")
        return None
