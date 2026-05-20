from .base_screen import BaseScreen
from core.vision import vision
import logging
import os
import time
import cv2
from datetime import datetime

logger = logging.getLogger(__name__)


def _draw_clicks(img, click_positions, colors, ox, oy, scale):
    for i, (key, cx, cy) in enumerate(click_positions or []):
        color = colors[i % len(colors)]
        label = key.split("/")[-1]
        px, py = int((cx - ox) * scale), int((cy - oy) * scale)
        cv2.circle(img, (px, py), 18, color, 3)
        cv2.putText(img, label, (px + 22, py + 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)

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
)

# For bail/recovery paths: tap whichever exit button is reachable.
EXIT_BATTLE_TEMPLATES = (
    "buttons/battle/btn_return_home",
    "buttons/battle/btn_end_battle",
)

SLOT_ICON_SCALES = (0.50, 0.60, 0.70, 0.80, 0.90, 1.00, 1.10, 1.20)


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
            self.ui_manager._poll_sleep(0.5)
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
            EXIT_BATTLE_TEMPLATES,
            timeout=5,
            silent=True,
            use_orb_fallback=False,
        )
        if loc:
            self.ui_manager.click(*loc)
            logger.info("Return Home tapped (battle bail recovery).")
            self.ui_manager._poll_sleep(3)
        self.close_popups()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _slot_deploy(self, deploy_cfg):
        slots = deploy_cfg.get("slots", [])
        if not slots:
            return False

        screen = self.ui_manager.get_screen()
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

        bar_crop = screen[by1:by2, bx1:bx2]
        bar_gray = None
        tap_interval = float(deploy_cfg.get("tap_interval", DEPLOY_TAP_INTERVAL))

        bar_center_y = (by1 + by2) // 2
        any_deployed = False
        debug_clicks = []
        for slot in slots:
            template_key = slot.get("template", "")
            configured_taps = int(slot.get("taps", 5))
            fixed_bar_x = slot.get("bar_x", 0)

            if fixed_bar_x:
                slot_cx = int(fixed_bar_x)
                slot_cy = int(slot.get("bar_y", bar_center_y))
                logger.info(f"[DEPLOY] '{template_key}' at ({slot_cx},{slot_cy}) [fixed], deploying {configured_taps}×")
            else:
                if bar_gray is None:
                    bar_gray = cv2.cvtColor(bar_crop, cv2.COLOR_BGR2GRAY)
                template = vision.cache.get(template_key)
                if template is None:
                    logger.debug(f"[DEPLOY] '{template_key}' not in cache, skipping")
                    continue

                score, scaled, result_map = vision._find_best_scale(
                    bar_gray, template, threshold=0.50, scales=SLOT_ICON_SCALES,
                )
                if result_map is None or scaled is None:
                    logger.debug(f"[DEPLOY] '{template_key}' not found in bar (score={score:.3f})")
                    continue

                _, _, _, max_loc = cv2.minMaxLoc(result_map)
                th, tw = scaled.shape[:2]
                slot_cx = int(max_loc[0] + tw // 2 + bx1)
                slot_cy = int(max_loc[1] + th // 2 + by1)
                logger.info(f"[DEPLOY] '{template_key}' at ({slot_cx},{slot_cy}) score={score:.2f}, deploying {configured_taps}×")

            debug_clicks.append((template_key, slot_cx, slot_cy))
            self.ui_manager.click(slot_cx, slot_cy)
            self.ui_manager._poll_sleep(0.3)

            self._execute_slot_strategy(slot, deploy_cfg, configured_taps, tap_interval)
            any_deployed = True

        self._save_bar_debug(screen, bar_crop, by1, by2, bx1, bx2, debug_clicks)
        return any_deployed

    def _save_bar_debug(self, screen, bar_crop, by1, by2, bx1, bx2, click_positions=None):
        if not logger.isEnabledFor(logging.DEBUG):
            return
        try:
            out_dir = os.path.join("coc_bot", "logs", "debug")
            os.makedirs(out_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            colors = [(0, 80, 255), (255, 80, 0), (0, 220, 220), (220, 0, 220)]

            canvas = screen.copy()
            cv2.rectangle(canvas, (bx1, by1), (bx2, by2), (0, 255, 0), 2)
            _draw_clicks(canvas, click_positions, colors, 0, 0, 1)
            cv2.imwrite(os.path.join(out_dir, f"bar_deploy_{ts}.png"), canvas)

            zoom = 3
            zoomed = cv2.resize(bar_crop, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_NEAREST)
            _draw_clicks(zoomed, click_positions, colors, bx1, by1, zoom)
            cv2.imwrite(os.path.join(out_dir, f"bar_deploy_{ts}_zoom.png"), zoomed)
            logger.debug(f"[DEPLOY] Bar debug saved: {out_dir}/bar_deploy_{ts}*.png")
        except Exception as e:
            logger.debug(f"[DEPLOY] Bar debug save failed: {e}")

    def _tap_line(self, x_start, x_end, y, taps, interval):
        step = (x_end - x_start) / max(taps - 1, 1)
        for i in range(taps):
            self.ui_manager.click(int(x_start + i * step), y)
            self.ui_manager._poll_sleep(interval)

    def _execute_slot_strategy(self, slot_cfg, deploy_cfg, taps, tap_interval):
        strategy = slot_cfg.get("strategy", "line")

        if strategy == "points":
            pts = slot_cfg.get("points", [])
            if not pts:
                logger.warning(f"[DEPLOY] strategy='points' but no points configured for '{slot_cfg.get('template', '?')}'")
            else:
                for i in range(taps):
                    pt = pts[i % len(pts)]
                    self.ui_manager.click(int(pt[0]), int(pt[1]))
                    self.ui_manager._poll_sleep(tap_interval)
        else:
            y       = int(slot_cfg.get("y",       deploy_cfg.get("battlefield_y",       750)))
            x_start = int(slot_cfg.get("x_start", deploy_cfg.get("battlefield_x_start", 300)))
            x_end   = int(slot_cfg.get("x_end",   deploy_cfg.get("battlefield_x_end",  1300)))
            self._tap_line(x_start, x_end, y, taps, tap_interval)

    def _sweep_deploy(self, deploy_cfg):
        y = int(deploy_cfg.get("y", 820))
        x_start = int(deploy_cfg.get("x_start", 300))
        x_end = int(deploy_cfg.get("x_end", 1300))
        taps = int(deploy_cfg.get("taps", 30))
        logger.info(f"[DEPLOY] Sweep: {taps} taps along y={y} from x={x_start} to x={x_end}.")
        self._tap_line(x_start, x_end, y, taps, DEPLOY_TAP_INTERVAL)
