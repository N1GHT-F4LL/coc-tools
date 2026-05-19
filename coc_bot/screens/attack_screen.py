from .base_screen import BaseScreen
from .battle_screen import BattleScreen
from core.ocr import read_number_with_confidence
from core.vision import vision
import logging
import time
import os
from datetime import datetime
import cv2

logger = logging.getLogger(__name__)

# How many consecutive bases to skip before giving up the cycle.
MAX_SKIP = 50
LOOT_BOUNDS = {
    "gold": (0, 3000000),
    "elixir": (0, 3000000),
    "dark_elixir": (0, 50000),
}
LOOT_ICON_TEMPLATES = {
    "gold": "icons/resources/icon_gold",
    "elixir": "icons/resources/icon_elixir",
    "dark_elixir": "icons/resources/icon_dark_elixir",
}
LOOT_ICON_CANDIDATE_TEMPLATES = {
    "gold": (
        "icons/resources/icon_gold",
        "buildings/resource_collectors/icon_gold_mine_full",
        "buildings/storages/icon_gold",
    ),
    "elixir": (
        "icons/resources/icon_elixir",
        "buildings/resource_collectors/icon_elixir_collector_full",
        "buildings/storages/icon_elixir",
    ),
    "dark_elixir": (
        "icons/resources/icon_dark_elixir",
        "buildings/resource_collectors/icon_dark_elixir_drill_full",
        "buildings/storages/icon_de",
    ),
}

FIND_A_MATCH_TEMPLATES = (
    "buttons/attack/btn_find_a_match",
)
NEXT_ENEMY_TEMPLATES = ("buttons/attack/btn_next_enemy",)
START_MATCH_TEMPLATES = ("buttons/attack/btn_attack",)
SCOUT_READY_TEMPLATES = (
    "buttons/attack/btn_next_enemy",
)
RETURN_HOME_TEMPLATES = (
    "buttons/battle/btn_return_home",
    "buttons/battle/btn_end_battle",
)
FIND_A_MATCH_THRESHOLD = 0.65
LOOT_ICON_SCALES = (0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.75, 1.00)


class AttackScreen(BaseScreen):
    def __init__(self, ui_manager, settings):
        super().__init__(ui_manager)
        self.settings = settings

    def is_current_screen(self):
        found = self.ui_manager.scan_all(
            self._existing_templates(FIND_A_MATCH_TEMPLATES),
            use_orb_fallback=False,
        )
        return bool(found)

    def run_attack_cycle(self):
        """Full farm attack cycle: find match -> evaluate loot -> attack -> deploy -> return.

        Called from the main loop when on the home screen. Returns when back on the
        home screen (or after a bail-out recovery). A missing template is treated as
        "not ready" and the cycle exits cleanly without crashing the bot.
        """
        farm = self.settings.get("farm", {})
        attack_cfg = self.settings.get("attack", {})
        # Correct game flow:
        # Home Attack -> Find a Match -> Attack! (start matchmaking) -> Scout -> OCR/Next.

        # --- step 1: tap the Attack! button on the home screen ---
        loc = self.ui_manager.wait_until_appears(
            "buttons/home/btn_attack",
            timeout=5,
            silent=True,
        )
        if not loc:
            logger.debug("Attack button not found; skipping attack cycle.")
            return
        self.ui_manager.click(*loc)
        logger.info("Tapped Attack! button.")

        # --- step 2: wait for the Find a Match preparation screen ---
        loc = self._wait_until_any_appears(
            FIND_A_MATCH_TEMPLATES,
            timeout=15,
            threshold=FIND_A_MATCH_THRESHOLD,
            use_orb_fallback=False,
            validator=self._is_find_match_loc_valid,
        )
        if not loc:
            logger.warning("Find a Match button not found - bailing out of attack cycle.")
            self._bail()
            return

        self.ui_manager.click(*loc)
        logger.info("Tapped Find a Match.")

        # Step 3: tap green Attack! button to start finding an opponent.
        if not self._tap_start_match_attack():
            logger.warning("Start-match Attack button not found after Find a Match - bailing.")
            self._bail()
            return

        # Wait until matchmaking lands on a real opponent scout screen.
        scout_loc = self._wait_until_any_appears(
            SCOUT_READY_TEMPLATES,
            timeout=35,
            use_orb_fallback=False,
        )
        if not scout_loc:
            logger.warning("Scout screen not detected after Find a Match - bailing.")
            self._bail()
            return
        skips = 0
        while skips <= MAX_SKIP:
            # Ensure scout UI has settled before OCR.
            time.sleep(1.0)

            screen = self.ui_manager.device.get_screen()
            if screen is None:
                logger.warning("No screen after match load - bailing.")
                self._bail()
                return

            # --- step 4: OCR the loot numbers ---
            loot, conf = self._read_loot(screen)
            logger.info(
                f"Enemy loot  gold={loot['gold']:,} (c={conf['gold']:.2f})  "
                f"elixir={loot['elixir']:,} (c={conf['elixir']:.2f})  "
                f"dark={loot['dark_elixir']:,} (c={conf['dark_elixir']:.2f})"
            )

            # --- step 5: decide hold attack or skip base ---
            if self._meets_threshold(loot, farm):
                logger.info("Loot meets threshold - keeping this base and attacking.")
                break

            logger.info("Loot below threshold - skipping base.")
            loc = self._wait_until_any_appears(
                NEXT_ENEMY_TEMPLATES,
                timeout=5,
                use_orb_fallback=False,
                validator=self._is_next_enemy_loc_valid,
            )
            if not loc:
                logger.warning("Next button not found - bailing.")
                self._bail()
                return
            self.ui_manager.click(*loc)
            logger.debug("Tapped Next Enemy.")
            ready = self._wait_until_any_appears(
                SCOUT_READY_TEMPLATES,
                timeout=20,
                silent=True,
                use_orb_fallback=False,
            )
            if not ready:
                logger.warning("Scout screen not ready after Next Enemy - bailing.")
                self._bail()
                return
            skips += 1
        else:
            logger.warning(f"Reached max skips ({MAX_SKIP}) - bailing.")
            self._bail()
            return

        # --- step 5: wait for battle screen, deploy troops, wait for end ---
        battle = BattleScreen(self.ui_manager)
        if not battle.wait_until_entered(timeout=15):
            logger.warning("Battle screen not detected after loot threshold — bailing.")
            self._bail()
            return

        battle.deploy_troops(attack_cfg.get("deploy", {}))

        loc = battle.wait_for_end()
        if not loc:
            logger.warning("Battle end timeout.")
            battle.bail()
            return

        battle.tap_return_home(loc)
        time.sleep(3)
        self.close_popups()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_loot(self, screen):
        result = {"gold": 0, "elixir": 0, "dark_elixir": 0}
        conf = {"gold": 0.0, "elixir": 0.0, "dark_elixir": 0.0}
        debug_regions = {}
        attack_cfg = self.settings.get("attack", {})
        by_icon_cfg = attack_cfg.get("loot_by_icon", {})
        icon_threshold = float(by_icon_cfg.get("threshold", 0.62))
        x_start = int(by_icon_cfg.get("x_start_offset", 18))
        x_end = int(by_icon_cfg.get("x_end_offset", 236))
        y_half = int(by_icon_cfg.get("y_half_height", 19))
        min_icon_conf = float(by_icon_cfg.get("min_icon_confidence", 0.55))
        per_resource = by_icon_cfg.get("per_resource", {})
        search_roi = by_icon_cfg.get("search_roi", [0, 70, 420, 360])
        loot_regions = attack_cfg.get("loot_regions", {})
        detected_icon_regions = self._regions_from_resource_icons(
            screen,
            search_roi=search_roi,
            loot_regions=loot_regions,
            x_start_offset=x_start,
            x_end_offset=x_end,
            y_half_height=y_half,
            per_resource_cfg=per_resource,
        )

        for key in result:
            key_cfg = per_resource.get(key, {}) if isinstance(per_resource, dict) else {}
            key_threshold = float(key_cfg.get("threshold", icon_threshold))
            key_x_start = int(key_cfg.get("x_start_offset", x_start))
            key_x_end = int(key_cfg.get("x_end_offset", x_end))
            key_y_half = int(key_cfg.get("y_half_height", y_half))
            icon_region = detected_icon_regions.get(key)
            if icon_region is None:
                icon_region = self._region_from_icon(
                    screen,
                    key,
                    threshold=key_threshold,
                    x_start_offset=key_x_start,
                    x_end_offset=key_x_end,
                    y_half_height=key_y_half,
                    search_roi=search_roi,
                )
            fallback_region = loot_regions.get(key)
            if icon_region and fallback_region and len(fallback_region) == 4:
                # Keep icon-anchored y band, but widen x using fallback to avoid
                # clipping leading digits when icon center jitters to the right.
                ix1, iy1, ix2, iy2 = [int(v) for v in icon_region]
                fx1, _fy1, fx2, _fy2 = [int(v) for v in fallback_region]
                icon_region = [min(ix1, fx1), iy1, max(ix2, fx2), iy2]

            candidate_regions = []
            if icon_region:
                candidate_regions.append(icon_region)
            if fallback_region and (
                not icon_region or tuple(icon_region) != tuple(fallback_region)
            ):
                candidate_regions.append(fallback_region)

            min_v, max_v = LOOT_BOUNDS.get(key, (0, None))
            best_val = None
            best_conf = 0.0
            best_region = None
            for idx, region in enumerate(candidate_regions):
                val, c = read_number_with_confidence(
                    screen,
                    tuple(region),
                    min_value=min_v,
                    max_value=max_v,
                    prefer_longest=(key != "dark_elixir"),
                    prefer_consensus=(key == "dark_elixir"),
                )
                if val is None:
                    continue
                # Prefer icon-anchored region once it produces a plausible read.
                # Fallback region is only allowed to replace it when icon confidence is weak.
                is_icon_region = bool(icon_region) and idx == 0 and tuple(region) == tuple(icon_region)
                if is_icon_region:
                    best_val = val
                    best_conf = c
                    best_region = list(region)
                    continue
                if best_region is not None and icon_region and tuple(best_region) == tuple(icon_region) and best_conf >= min_icon_conf:
                    continue
                if (
                    best_val is None
                    or c > best_conf
                    or (abs(c - best_conf) < 1e-6 and val > best_val)
                ):
                    best_val = val
                    best_conf = c
                    best_region = list(region)

            if best_val is not None:
                result[key] = best_val
                conf[key] = best_conf
            if candidate_regions:
                debug_regions[key] = {
                    "icon_region": icon_region,
                    "fallback_region": fallback_region,
                    "used_candidates": candidate_regions,
                    "selected_region": best_region,
                    "value": result[key],
                    "conf": conf[key],
                }
        self._dump_loot_debug(screen, debug_regions, attack_cfg)
        return result, conf

    def _regions_from_resource_icons(
        self,
        screen,
        search_roi,
        loot_regions=None,
        x_start_offset=18,
        x_end_offset=236,
        y_half_height=19,
        per_resource_cfg=None,
    ):
        h, w = screen.shape[:2]
        out = {}
        keys = ("gold", "elixir", "dark_elixir")
        # Prefer icon matches close to expected row centers from fallback regions.
        expected_y = {}
        for key in keys:
            reg = (loot_regions or {}).get(key)
            if reg and len(reg) == 4:
                expected_y[key] = int((int(reg[1]) + int(reg[3])) / 2)

        for key in keys:
            target_y = expected_y.get(key)
            key_cfg = (per_resource_cfg or {}).get(key, {}) if isinstance(per_resource_cfg, dict) else {}
            key_threshold = float(key_cfg.get("threshold", 0.56))
            logger.debug(
                f"[ICON_REGION] {key}: search_roi={search_roi}, target_y={target_y}, threshold={key_threshold:.3f}, "
                f"offsets=({key_cfg.get('x_start_offset', x_start_offset)}, {key_cfg.get('x_end_offset', x_end_offset)}), "
                f"y_half={key_cfg.get('y_half_height', y_half_height)}"
            )
            icon = self._find_best_resource_icon_match(
                screen,
                key,
                search_roi=search_roi,
                target_y=target_y,
                threshold=key_threshold,
            )
            if not icon:
                logger.debug(f"[ICON_REGION] {key}: NO ICON FOUND")
                continue
            cx, cy, _score = icon
            logger.debug(f"[ICON_REGION] {key}: ICON CENTER cx={cx}, cy={cy}")

            key_x_start = int(key_cfg.get("x_start_offset", x_start_offset))
            key_x_end = int(key_cfg.get("x_end_offset", x_end_offset))
            key_y_half = int(key_cfg.get("y_half_height", y_half_height))

            x1 = max(0, min(w - 1, cx + key_x_start))
            x2 = max(0, min(w, cx + key_x_end))
            y1 = max(0, min(h - 1, cy - key_y_half))
            y2 = max(0, min(h, cy + key_y_half))
            logger.debug(f"[ICON_REGION] {key}: REGION [{x1}, {y1}, {x2}, {y2}] (offsets: x_start={key_x_start}, x_end={key_x_end})")
            if x2 > x1 and y2 > y1:
                out[key] = [int(x1), int(y1), int(x2), int(y2)]
        return out

    def _find_best_resource_icon_match(self, screen, loot_key, search_roi=None, target_y=None, threshold=0.56):
        templates = LOOT_ICON_CANDIDATE_TEMPLATES.get(loot_key, ())
        if not templates:
            logger.debug(f"[ICON_DEBUG] {loot_key}: no candidate templates configured")
            return None

        crop = screen
        roi_x1 = roi_y1 = 0
        if search_roi and len(search_roi) == 4:
            sx1, sy1, sx2, sy2 = [int(v) for v in search_roi]
            h, w = screen.shape[:2]
            sx1 = max(0, min(w - 1, sx1))
            sx2 = max(1, min(w, sx2))
            sy1 = max(0, min(h - 1, sy1))
            sy2 = max(1, min(h, sy2))
            if sx2 > sx1 and sy2 > sy1:
                crop = screen[sy1:sy2, sx1:sx2]
                roi_x1, roi_y1 = sx1, sy1

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        best = None
        max_y_delta = 18

        for tpl_name in templates:
            template = vision.cache.get(tpl_name)
            if template is None:
                logger.debug(f"[ICON_DEBUG] {loot_key}: template={tpl_name} missing from cache")
                continue
            score, scaled, result_map = vision._find_best_scale(
                gray,
                template,
                threshold=threshold,
                scales=LOOT_ICON_SCALES,
            )
            if result_map is None or scaled is None:
                logger.debug(f"[ICON_DEBUG] {loot_key}: template={tpl_name} produced no usable match map")
                continue
            _, _, _, max_loc = cv2.minMaxLoc(result_map)
            th, tw = scaled.shape[:2]
            cx = int(max_loc[0] + tw // 2 + roi_x1)
            cy = int(max_loc[1] + th // 2 + roi_y1)
            logger.debug(
                f"[ICON_DEBUG] {loot_key}: template={tpl_name}, score={score:.3f}, "
                f"match_center=({cx},{cy}), scaled_size=({tw}x{th}), roi_origin=({roi_x1},{roi_y1})"
            )
            if score < threshold:
                logger.debug(
                    f"[ICON_DEBUG] {loot_key}: template={tpl_name} rejected by score {score:.3f} < {threshold:.3f}"
                )
                continue
            if cx > 130 or cx < 8:
                logger.debug(f"[ICON_DEBUG] {loot_key}: REJECTED (cx out of bounds: {cx})")
                continue
            if target_y is not None and abs(cy - int(target_y)) > max_y_delta:
                logger.debug(
                    f"[ICON_DEBUG] {loot_key}: REJECTED (cy out of row band: cy={cy}, target_y={target_y}, max_y_delta={max_y_delta})"
                )
                continue

            # Prefer correct row; small penalty if y differs from expected.
            color_bonus = self._resource_color_bonus(screen, cx, cy, loot_key)
            rank = score + color_bonus
            if target_y is not None:
                rank -= min(abs(cy - int(target_y)), 60) * 0.01
            logger.debug(
                f"[ICON_DEBUG] {loot_key}: template={tpl_name}, rank={rank:.3f}, color_bonus={color_bonus:.3f}"
            )

            if best is None or rank > best[0]:
                best = (rank, cx, cy, float(score))
        if not best:
            logger.debug(f"[ICON_DEBUG] {loot_key}: no template survived threshold/bounds checks")
            return None
        logger.debug(f"[ICON_DEBUG] {loot_key}: SELECTED cx={best[1]}, cy={best[2]}, score={best[3]}")
        return (best[1], best[2], best[3])

    def _resource_color_bonus(self, screen, cx, cy, loot_key):
        """Small color prior to separate lookalike icons in grayscale matching."""
        h, w = screen.shape[:2]
        r = 8
        x1 = max(0, cx - r)
        x2 = min(w, cx + r + 1)
        y1 = max(0, cy - r)
        y2 = min(h, cy + r + 1)
        if x2 <= x1 or y2 <= y1:
            return 0.0

        patch = screen[y1:y2, x1:x2]
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        mean_h, mean_s, mean_v, _ = cv2.mean(hsv)

        if loot_key == "elixir":
            # Pink/purple: hue around 135-175 (OpenCV hue space), high saturation.
            if 130 <= mean_h <= 178 and mean_s >= 70 and mean_v >= 50:
                return 0.08
            return -0.08

        if loot_key == "dark_elixir":
            # Dark droplet: low brightness, usually low-mid saturation.
            if mean_v <= 75:
                return 0.08
            return -0.08

        if loot_key == "gold":
            # Yellow-ish: hue around 15-40 with moderate/high saturation.
            if 12 <= mean_h <= 42 and mean_s >= 70 and mean_v >= 60:
                return 0.06
            return -0.06

        return 0.0

    def _dump_loot_debug(self, screen, debug_regions, attack_cfg):
        if not attack_cfg.get("debug_loot_regions", False):
            return
        if not debug_regions:
            return

        out_dir = os.path.join("coc_bot", "logs", "debug", "loot_regions")
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        canvas = screen.copy()
        colors = {
            "gold": (0, 255, 255),         # cyan (bright)
            "elixir": (0, 255, 0),         # green (bright)
            "dark_elixir": (0, 0, 255)     # red (bright)
        }
        for key, meta in debug_regions.items():
            color = colors.get(key, (0, 255, 0))
            selected_region = meta.get("selected_region")
            icon_region = meta.get("icon_region")
            fallback_region = meta.get("fallback_region")
            for region in meta.get("used_candidates", []):
                x1, y1, x2, y2 = [int(v) for v in region]
                thickness = 3 if selected_region and tuple(region) == tuple(selected_region) else 1
                cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness)
                
                # Determine region type (ICON or FALLBACK)
                region_type = "?"
                if icon_region and tuple(region) == tuple(icon_region):
                    region_type = "ICON"
                elif fallback_region and tuple(region) == tuple(fallback_region):
                    region_type = "FALLBACK"
                
                label = f"{key} {region_type}: {meta['value']} c={meta['conf']:.2f}"
                cv2.putText(
                    canvas,
                    label,
                    (x1, max(18, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    color,
                    1,
                    cv2.LINE_AA,
                )
                crop = screen[y1:y2, x1:x2]
                if crop.size > 0:
                    crop_path = os.path.join(out_dir, f"{ts}_{key}_{x1}_{y1}_{x2}_{y2}.png")
                    cv2.imwrite(crop_path, crop)

        full_path = os.path.join(out_dir, f"{ts}_full.png")
        cv2.imwrite(full_path, canvas)
        logger.debug(f"Loot debug images saved: {out_dir}")

    def _region_from_icon(
        self,
        screen,
        loot_key,
        threshold=0.62,
        x_start_offset=18,
        x_end_offset=236,
        y_half_height=19,
        search_roi=None,
    ):
        template = LOOT_ICON_TEMPLATES.get(loot_key)
        if not template:
            return None

        crop = screen
        roi_x1 = roi_y1 = 0
        if search_roi and len(search_roi) == 4:
            sx1, sy1, sx2, sy2 = [int(v) for v in search_roi]
            h, w = screen.shape[:2]
            sx1 = max(0, min(w - 1, sx1))
            sx2 = max(1, min(w, sx2))
            sy1 = max(0, min(h - 1, sy1))
            sy2 = max(1, min(h, sy2))
            if sx2 > sx1 and sy2 > sy1:
                crop = screen[sy1:sy2, sx1:sx2]
                roi_x1, roi_y1 = sx1, sy1

        icon_loc = vision.find_template(
            crop,
            template,
            threshold=threshold,
            use_orb_fallback=False,
        )
        if not icon_loc:
            return None

        cx = icon_loc[0] + roi_x1
        cy = icon_loc[1] + roi_y1
        h, w = screen.shape[:2]
        x1 = max(0, min(w - 1, cx + x_start_offset))
        x2 = max(0, min(w, cx + x_end_offset))
        y1 = max(0, min(h - 1, cy - y_half_height))
        y2 = max(0, min(h, cy + y_half_height))
        if x2 <= x1 or y2 <= y1:
            return None
        return [int(x1), int(y1), int(x2), int(y2)]

    def _meets_threshold(self, loot, farm):
        return (
            loot["gold"] >= farm.get("min_gold", 0)
            and loot["elixir"] >= farm.get("min_elixir", 0)
            and loot["dark_elixir"] >= farm.get("min_dark_elixir", 0)
        )

    def _tap_start_match_attack(self):
        loc = self._wait_until_any_appears(
            START_MATCH_TEMPLATES,
            timeout=5,
            use_orb_fallback=False,
        )
        if not loc:
            return False
        self.ui_manager.click(*loc)
        return True

    def _bail(self):
        """Best-effort recovery: tap Return Home if visible, then close popups."""
        loc = self._wait_until_any_appears(RETURN_HOME_TEMPLATES, timeout=5, silent=True, use_orb_fallback=False)
        if loc:
            self.ui_manager.click(*loc)
            logger.info("Return Home tapped (bail recovery).")
            time.sleep(3)
        self.close_popups()

    def _is_find_match_loc_valid(self, loc):
        x, y = loc
        # Find a Match is expected in the lower-left panel area.
        return 100 <= x <= 700 and 520 <= y <= 860

    def _is_next_enemy_loc_valid(self, loc):
        x, y = loc
        # Next Enemy appears on the right side during scout screen.
        return 900 <= x <= 1595 and 280 <= y <= 860

    def _is_return_home_loc_valid(self, loc):
        x, y = loc
        # Return Home appears near the center-lower area on results screen.
        return 350 <= x <= 1250 and 350 <= y <= 860
