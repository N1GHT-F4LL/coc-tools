import json
import time
import cv2
import os
import logging
from datetime import datetime
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

    # Check if CoC is running and in foreground; launch or bring to foreground if needed
    logger.info("Checking Clash of Clans status...")
    coc_package = "com.supercell.clashofclans"
    
    if device.is_app_running(coc_package):
        logger.info("CoC is running.")
        if not device.is_app_foreground(coc_package):
            logger.warning("CoC is running but in background. Bringing to foreground...")
            device.bring_app_to_foreground(coc_package)
    else:
        logger.warning("CoC is not running. Launching game...")
        device.launch_game()

    ui_manager = UIManager(humanize, device)

    vision.load_assets("coc_bot/assets")
    
    # Capture initial screen for debugging
    logger.info("Capturing initial screen for debugging...")
    initial_screen = device.get_screen()
    if initial_screen is not None:
        debug_dir = os.path.join('coc_bot', 'logs', 'debug')
        os.makedirs(debug_dir, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        debug_path = os.path.join(debug_dir, f"initial_screen_{ts}.png")
        cv2.imwrite(debug_path, initial_screen)
        logger.info(f"Initial screen saved: {debug_path}")

    home_screen = HomeScreen(ui_manager)
    logger.info("Bot starting main loop...")
    
    # Wait for home screen to load and stabilize
    logger.info("Waiting for home screen to load...")
    max_wait = 10
    start_wait = time.time()
    while time.time() - start_wait < max_wait:
        if home_screen.is_current_screen():
            logger.info("Home screen detected!")
            break
        logger.info("Not on home screen yet, waiting...")
        time.sleep(1)
    else:
        logger.warning(f"Home screen not detected after {max_wait} seconds. Continuing anyway...")
    
    # Main bot loop
    loop_count = 0
    while loop_count < 3:
        logger.info(f"--- Loop {loop_count} ---")
        
        # Close any popups if present
        logger.info("Attempting to close popups...")
        home_screen.close_popups()
        
        # Check home screen and perform actions
        if home_screen.is_current_screen():
            logger.info("On Home Screen. Collecting resources...")
            home_screen.collect_resources()
        else:
            logger.warning("Not on home screen, attempting recovery...")
            
        time.sleep(2)
        loop_count += 1
    
    logger.info("Test loops finished.")

if __name__ == "__main__":
    main()
