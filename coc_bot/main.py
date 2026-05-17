import json
import time
import cv2
import os
import logging
from core.humanize import Humanize
from core.ui_manager import UIManager
from core.vision import vision
from core.device import Device
from screens.home_screen import HomeScreen

def load_settings():
    with open("coc_bot/settings.json", "r") as f:
        return json.load(f)

def main():
    settings = load_settings()
    humanize = Humanize(settings)
    # Configure logging
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
    logger = logging.getLogger(__name__)

    # Instantiate device at runtime to avoid import-time side-effects.
    device = Device()
    # If adb is not available, abort early with instructions.
    if not getattr(device, 'available', False):
        logger.error("\n' adb' not found in your PATH. The bot requires adb to interact with a device.")
        logger.error("Install Android platform-tools and ensure 'adb' is on your PATH, then re-run this script.")
        logger.error("On Windows, you can download from: https://developer.android.com/studio/releases/platform-tools")
        return

    # Optionally perform connection checks / wake here.
    device._check_connection()

    ui_manager = UIManager(humanize, device)

    vision.load_assets("coc_bot/assets")

    home_screen = HomeScreen(ui_manager)
    logger.info("Bot starting main loop...")
    loop_count = 0
    while loop_count < 3:
        logger.info(f"--- Loop {loop_count} ---")
        home_screen.close_popups()
        if home_screen.is_current_screen():
            logger.info("On Home Screen. Collecting...")
            home_screen.collect_resources()
        else:
            logger.warning("Not on home screen, attempting recovery...")
            
        time.sleep(2)
        loop_count += 1
    
    logger.info("Test loops finished.")

if __name__ == "__main__":
    main()
