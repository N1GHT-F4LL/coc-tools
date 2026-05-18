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
    coc_package = "com.supercell.clashofclans"
    if not device.ensure_coc_ready(coc_package, settings, save_settings, logger):
        return

    ui_manager = UIManager(humanize, device)
    vision.load_assets("coc_bot/assets")

    logger.info("Capturing initial screen for debugging...")
    initial_screen = device.get_screen()
    if initial_screen is not None:
        debug_dir = os.path.join('coc_bot', 'logs', 'debug')
        os.makedirs(debug_dir, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        debug_path = os.path.join(debug_dir, f"initial_screen_{ts}.png")
        cv2.imwrite(debug_path, initial_screen)
        logger.info(f"Initial screen saved: {debug_path}")
    else:
        logger.error("Failed to capture initial screen. Device may be disconnected.")
        return

    home_screen = HomeScreen(ui_manager)
    logger.info("Bot starting main loop...")
    logger.info("Waiting for home screen to load...")

    max_wait = 10
    start_wait = time.time()
    home_ready = False
    while time.time() - start_wait < max_wait:
        if home_screen.is_current_screen():
            logger.info("Home screen detected!")
            home_ready = True
            break
        logger.info("Not on home screen yet, waiting...")
        time.sleep(1)
    else:
        logger.warning(f"Home screen not detected after {max_wait} seconds. Continuing anyway...")

    # Default CoC zoom hides edge collectors. CoC clamps at a max zoom-out
    # level which auto-centers on the Town Hall; a few repeats reliably hits
    # that floor regardless of where the camera started.
    if home_ready:
        logger.info("Zooming out for overall village view...")
        device.pinch('out', span_pixels=600, repeats=3)
        time.sleep(1.0)

    HOME_DETECT_MAX_MISSES = 2
    loop_count = 0
    home_misses = 0
    while loop_count < 3:
        logger.info(f"--- Loop {loop_count} ---")
        if home_screen.is_current_screen():
            home_misses = 0
            logger.info("On Home Screen. Collecting resources...")
            home_screen.collect_resources()
        else:
            home_misses += 1
            logger.warning(f"Not on home screen ({home_misses}/{HOME_DETECT_MAX_MISSES} consecutive misses). Closing popups...")
            home_screen.close_popups()
            if home_misses >= HOME_DETECT_MAX_MISSES:
                logger.warning("close_popups did not recover home. Restarting game...")
                if not device.restart_game(coc_package):
                    logger.error("Game restart failed. Stopping bot.")
                    return
                home_misses = 0

        time.sleep(2)
        loop_count += 1

    logger.info("Test loops finished.")


if __name__ == "__main__":
    main()
