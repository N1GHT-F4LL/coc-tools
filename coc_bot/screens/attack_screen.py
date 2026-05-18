from .base_screen import BaseScreen
from core.ocr import read_number
from core.vision import vision
import logging
import time

logger = logging.getLogger(__name__)

# How many consecutive bases to skip before giving up the cycle.
MAX_SKIP = 50
# Time between each troop-deployment tap (seconds).
DEPLOY_TAP_INTERVAL = 0.15
# Seconds to wait for a battle to fully resolve before timing out.
BATTLE_TIMEOUT = 180
LOOT_BOUNDS = {
    "gold": (0, 3000000),
    "elixir": (0, 3000000),
    "dark_elixir": (0, 50000),
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
            loot = self._read_loot(screen, attack_cfg.get("loot_regions", {}))
            logger.info(
                f"Enemy loot  gold={loot['gold']:,}  "
                f"elixir={loot['elixir']:,}  "
                f"dark={loot['dark_elixir']:,}"
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
            logger.info("Tapped Next Enemy.")
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

        # --- step 5: deploy troops along the chosen edge ---
        time.sleep(1.5)  # battle intro animation
        self._deploy_troops(attack_cfg.get("deploy", {}))

        # --- step 6: wait for battle to end ---
        logger.info(f"Troops deployed. Waiting up to {BATTLE_TIMEOUT}s for battle end...")
        loc = self._wait_until_any_appears(
            RETURN_HOME_TEMPLATES,
            timeout=BATTLE_TIMEOUT,
            use_orb_fallback=False,
            validator=self._is_return_home_loc_valid,
        )
        if not loc:
            logger.warning("Return Home button not found after battle timeout.")
            self._bail()
            return

        self.ui_manager.click(*loc)
        logger.info("Tapped Return Home.")

        # --- step 7: wait for results screens to clear ---
        time.sleep(3)
        self.close_popups()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_loot(self, screen, loot_regions):
        result = {"gold": 0, "elixir": 0, "dark_elixir": 0}
        for key in result:
            region = loot_regions.get(key)
            if region:
                min_v, max_v = LOOT_BOUNDS.get(key, (0, None))
                val = read_number(screen, tuple(region), min_value=min_v, max_value=max_v)
                if val is not None:
                    result[key] = val
        return result

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

    def _deploy_troops(self, deploy_cfg):
        """Sweep taps along the deployment edge to drop all troops."""
        y = deploy_cfg.get("y", 820)
        x_start = deploy_cfg.get("x_start", 300)
        x_end = deploy_cfg.get("x_end", 1300)
        taps = deploy_cfg.get("taps", 30)

        logger.info(f"Deploying {taps} taps along y={y} from x={x_start} to x={x_end}.")
        step = (x_end - x_start) / max(taps - 1, 1)
        for i in range(taps):
            x = int(x_start + i * step)
            self.ui_manager.click(x, y)
            time.sleep(DEPLOY_TAP_INTERVAL)

    def _bail(self):
        """Best-effort recovery: tap Return Home if visible, then close popups."""
        loc = self._wait_until_any_appears(RETURN_HOME_TEMPLATES, timeout=5, silent=True, use_orb_fallback=False)
        if loc:
            self.ui_manager.click(*loc)
            logger.info("Return Home tapped (bail recovery).")
            time.sleep(3)
        self.close_popups()

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
