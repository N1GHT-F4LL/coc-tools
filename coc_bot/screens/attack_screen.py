from .base_screen import BaseScreen
from core.ocr import read_number
import logging
import time

logger = logging.getLogger(__name__)

# How many consecutive bases to skip before giving up the cycle.
MAX_SKIP = 50
# Time between each troop-deployment tap (seconds).
DEPLOY_TAP_INTERVAL = 0.15
# Seconds to wait for a battle to fully resolve before timing out.
BATTLE_TIMEOUT = 180


class AttackScreen(BaseScreen):
    def __init__(self, ui_manager, settings):
        super().__init__(ui_manager)
        self.settings = settings

    def is_current_screen(self):
        found = self.ui_manager.scan_all(["btn_find_a_match"], use_orb_fallback=False)
        return bool(found)

    def run_attack_cycle(self):
        """Full farm attack cycle: find match → evaluate loot → attack → deploy → return.

        Called from the main loop when on the home screen. Returns when back on the
        home screen (or after a bail-out recovery). A missing template is treated as
        'not ready' and the cycle exits cleanly without crashing the bot.
        """
        farm = self.settings.get("farm", {})
        attack_cfg = self.settings.get("attack", {})

        # --- step 1: tap the Attack! button on the home screen ---
        loc = self.ui_manager.wait_until_appears("home_attack_button_1600x900", timeout=5,
                                                  silent=True)
        if not loc:
            logger.debug("Attack button not found; skipping attack cycle.")
            return
        self.ui_manager.click(*loc)
        logger.info("Tapped Attack! button.")

        # --- step 2: wait for the Find a Match preparation screen ---
        loc = self.ui_manager.wait_until_appears("btn_find_a_match", timeout=15)
        if not loc:
            logger.warning("Find a Match button not found — bailing out of attack cycle.")
            self._bail()
            return

        skips = 0
        while skips <= MAX_SKIP:
            self.ui_manager.click(*loc)
            logger.info("Searching for enemy base..." if skips else "Tapped Find a Match.")

            # Allow the enemy base preview to load before reading loot.
            time.sleep(2.5)

            screen = self.ui_manager.device.get_screen()
            if screen is None:
                logger.warning("No screen after match load — bailing.")
                self._bail()
                return

            # --- step 3: OCR the loot numbers ---
            loot = self._read_loot(screen, attack_cfg.get("loot_regions", {}))
            logger.info(
                f"Enemy loot  gold={loot['gold']:,}  "
                f"elixir={loot['elixir']:,}  "
                f"dark={loot['dark_elixir']:,}"
            )

            # --- step 4: decide attack or skip ---
            if self._meets_threshold(loot, farm):
                logger.info("Loot meets threshold — attacking!")
                if not self._confirm_attack():
                    logger.warning("Attack confirm button not found — bailing.")
                    self._bail()
                    return
                break

            logger.info("Loot below threshold — skipping base.")
            loc = self.ui_manager.wait_until_appears("btn_next_enemy", timeout=5)
            if not loc:
                logger.warning("Next button not found — bailing.")
                self._bail()
                return
            skips += 1
        else:
            logger.warning(f"Reached max skips ({MAX_SKIP}) — bailing.")
            self._bail()
            return

        # --- step 5: deploy troops along the chosen edge ---
        time.sleep(1.5)  # battle intro animation
        self._deploy_troops(attack_cfg.get("deploy", {}))

        # --- step 6: wait for battle to end ---
        logger.info(f"Troops deployed. Waiting up to {BATTLE_TIMEOUT}s for battle end...")
        loc = self.ui_manager.wait_until_appears("btn_return_home", timeout=BATTLE_TIMEOUT)
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
                val = read_number(screen, tuple(region))
                if val is not None:
                    result[key] = val
        return result

    def _meets_threshold(self, loot, farm):
        return (
            loot["gold"] >= farm.get("min_gold", 0)
            and loot["elixir"] >= farm.get("min_elixir", 0)
            and loot["dark_elixir"] >= farm.get("min_dark_elixir", 0)
        )

    def _confirm_attack(self):
        loc = self.ui_manager.wait_until_appears("btn_attack_confirm", timeout=5)
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
        loc = self.ui_manager.wait_until_appears("btn_return_home", timeout=5, silent=True)
        if loc:
            self.ui_manager.click(*loc)
            logger.info("Return Home tapped (bail recovery).")
            time.sleep(3)
        self.close_popups()
