import json
import time
import cv2
import os
import logging
from datetime import datetime
from core.humanize import Humanize
from core.ui_manager import UIManager
from core.vision import vision
from core.device import bootstrap_device
from core.logging_utils import setup_logging
from screens.home_screen import HomeScreen

SETTINGS_PATH = "coc_bot/settings.json"
COC_PACKAGE = "com.supercell.clashofclans"
# Replaced by battle duration once the attack phase is implemented.
IDLE_CYCLE_SLEEP = 30
HOME_DETECT_MAX_MISSES = 2


def load_settings():
    with open(SETTINGS_PATH, "r") as f:
        return json.load(f)


def save_settings(settings):
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f, indent=2)


def main():
    settings = load_settings()
    humanize = Humanize(settings)
    setup_logging(level=logging.INFO)
    logger = logging.getLogger(__name__)

    device = bootstrap_device(settings, save_settings, logger)
    if device is None:
        return

    logger.info("Checking Clash of Clans status...")
    if not device.ensure_coc_ready(COC_PACKAGE, settings, save_settings, logger):
        return

    ui_manager = UIManager(humanize, device)
    vision.load_assets("coc_bot/assets")

    logger.info("Capturing initial screen for debugging...")
    initial_screen = device.get_screen()
    if initial_screen is not None:
        debug_dir = os.path.join('coc_bot', 'logs', 'debug')
        os.makedirs(debug_dir, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        cv2.imwrite(os.path.join(debug_dir, f"initial_screen_{ts}.png"), initial_screen)
    else:
        logger.error("Failed to capture initial screen. Device may be disconnected.")
        return

    home_screen = HomeScreen(ui_manager)

    logger.info("Waiting for home screen to load...")
    deadline = time.time() + 10
    while time.time() < deadline:
        if home_screen.is_current_screen():
            logger.info("Home screen detected.")
            logger.info("Zooming out for full village view...")
            device.pinch('out', span_pixels=600, repeats=1)
            time.sleep(1.0)
            break
        time.sleep(1)
    else:
        logger.warning("Home screen not detected after 10 s. Continuing anyway...")

    logger.info("Bot running. Press Ctrl+C to stop.")

    home_misses = 0
    cycle = 0

    try:
        while True:
            cycle += 1
            logger.info(f"--- Cycle {cycle} ---")

            if home_screen.is_current_screen():
                home_misses = 0
            else:
                home_misses += 1
                logger.warning(
                    f"Not on home screen ({home_misses}/{HOME_DETECT_MAX_MISSES}). "
                    "Closing popups..."
                )
                home_screen.close_popups()

                if home_misses >= HOME_DETECT_MAX_MISSES:
                    logger.warning("Popup recovery failed. Restarting game...")
                    if not device.restart_game(COC_PACKAGE):
                        logger.error("Game restart failed. Stopping bot.")
                        break
                    home_misses = 0
                    logger.info("Waiting 15 s for game to reload...")
                    time.sleep(15)
                    # Zoom out again after a restart so the village is centered.
                    if home_screen.is_current_screen():
                        device.pinch('out', span_pixels=600, repeats=1)
                        time.sleep(1.0)
                continue

            home_screen.collect_resources()

            # TODO: implement attack cycle
            # attack_screen.run_attack_cycle()

            logger.info(f"Cycle {cycle} complete. Next cycle in {IDLE_CYCLE_SLEEP}s...")
            time.sleep(IDLE_CYCLE_SLEEP)

    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C).")


if __name__ == "__main__":
    main()
