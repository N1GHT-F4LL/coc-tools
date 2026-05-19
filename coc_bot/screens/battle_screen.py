from .base_screen import BaseScreen
from core.vision import vision
import logging
import time
import cv2

logger = logging.getLogger(__name__)

BATTLE_TIMEOUT = 180
DEPLOY_TAP_INTERVAL = 0.15

# Anchors that appear at some point during the attack phase.
BATTLE_ANCHORS = (
    "buttons/battle/btn_end_battle",
    "buttons/battle/btn_surrender",
    "buttons/battle/btn_return_home",
)

RETURN_HOME_TEMPLATES = (
    "buttons/battle/btn_return_home",
    "buttons/battle/btn_end_battle",
)

# Small scales for troop bar icons, which are much smaller than vision templates
# captured from the village map.
SLOT_ICON_SCALES = (0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50)


class BattleScreen(BaseScreen):
    def is_current_screen(self):
        found = self.ui_manager.scan_all(
            self._existing_templates(BATTLE_ANCHORS),
            use_orb_fallback=False,
        )
        return bool(found)

    def wait_until_entered(self, timeout=15):
        """Poll until the battle UI is visible (replaces blind sleep before deploy)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_current_screen():
                return True
            time.sleep(0.5)
        return False

    def deploy_troops(self, deploy_cfg):
        mode = deploy_cfg.get("mode", "sweep")
        if mode == "slot":
            if not self._slot_deploy(deploy_cfg):
                logger.warning("[DEPLOY] No troop slots matched — falling back to sweep.")
                self._sweep_deploy(deploy_cfg)
        else:
            self._sweep_deploy(deploy_cfg)

    def wait_for_end(self, timeout=BATTLE_TIMEOUT):
        """Wait for a Return Home button and return its location, or None on timeout."""
        return self._wait_until_any_appears(
            RETURN_HOME_TEMPLATES,
            timeout=timeout,
            use_orb_fallback=False,
        )

    def tap_return_home(self, loc):
        self.ui_manager.click(*loc)
        logger.info("Tapped Return Home.")

    def bail(self):
        """Best-effort recovery: tap Return Home if visible, then close popups."""
        loc = self._wait_until_any_appears(
            RETURN_HOME_TEMPLATES,
            timeout=5,
            silent=True,
            use_orb_fallback=False,
        )
        if loc:
            self.ui_manager.click(*loc)
            logger.info("Return Home tapped (battle bail recovery).")
            time.sleep(3)
        self.close_popups()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _slot_deploy(self, deploy_cfg):
        """Find each configured troop icon in the bar, select it, deploy N times.

        Returns True if at least one slot was successfully deployed.
        """
        slots = deploy_cfg.get("slots", [])
        if not slots:
            return False

        screen = self.ui_manager.device.get_screen()
        if screen is None:
            return False

        bar_region = deploy_cfg.get("troop_bar_region", [200, 855, 1400, 910])
        bx1, by1, bx2, by2 = [int(v) for v in bar_region]
        h, w = screen.shape[:2]
        bx1 = max(0, min(w - 1, bx1))
        bx2 = max(1, min(w, bx2))
        by1 = max(0, min(h - 1, by1))
        by2 = max(1, min(h, by2))
        if bx2 <= bx1 or by2 <= by1:
            logger.warning("[DEPLOY] troop_bar_region invalid — skipping slot deploy.")
            return False

        bar_gray = cv2.cvtColor(screen[by1:by2, bx1:bx2], cv2.COLOR_BGR2GRAY)

        bf_y = int(deploy_cfg.get("battlefield_y", 750))
        bf_x_start = int(deploy_cfg.get("battlefield_x_start", 300))
        bf_x_end = int(deploy_cfg.get("battlefield_x_end", 1300))
        tap_interval = float(deploy_cfg.get("tap_interval", DEPLOY_TAP_INTERVAL))

        any_deployed = False
        for slot in slots:
            template_key = slot.get("template", "")
            taps = int(slot.get("taps", 5))
            template = vision.cache.get(template_key)
            if template is None:
                logger.debug(f"[DEPLOY] '{template_key}' not in cache, skipping slot")
                continue

            score, scaled, result_map = vision._find_best_scale(
                bar_gray,
                template,
                threshold=0.50,
                scales=SLOT_ICON_SCALES,
            )
            if result_map is None or scaled is None:
                logger.debug(f"[DEPLOY] '{template_key}' not found in troop bar (score={score:.3f})")
                continue

            _, _, _, max_loc = cv2.minMaxLoc(result_map)
            th, tw = scaled.shape[:2]
            slot_cx = int(max_loc[0] + tw // 2 + bx1)
            slot_cy = int(max_loc[1] + th // 2 + by1)

            logger.info(f"[DEPLOY] Found '{template_key}' at ({slot_cx},{slot_cy}), deploying {taps}×")
            self.ui_manager.click(slot_cx, slot_cy)
            time.sleep(0.3)

            step = (bf_x_end - bf_x_start) / max(taps - 1, 1)
            for i in range(taps):
                x = int(bf_x_start + i * step)
                self.ui_manager.click(x, bf_y)
                time.sleep(tap_interval)

            any_deployed = True

        return any_deployed

    def _sweep_deploy(self, deploy_cfg):
        y = int(deploy_cfg.get("y", 820))
        x_start = int(deploy_cfg.get("x_start", 300))
        x_end = int(deploy_cfg.get("x_end", 1300))
        taps = int(deploy_cfg.get("taps", 30))

        logger.info(f"[DEPLOY] Sweep: {taps} taps along y={y} from x={x_start} to x={x_end}.")
        step = (x_end - x_start) / max(taps - 1, 1)
        for i in range(taps):
            x = int(x_start + i * step)
            self.ui_manager.click(x, y)
            time.sleep(DEPLOY_TAP_INTERVAL)
