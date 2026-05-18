import json
import time
import cv2
import os
import logging
import sys
from datetime import datetime
from core.humanize import Humanize
from core.ui_manager import UIManager
from core.vision import vision
from core.device import bootstrap_device
from screens.home_screen import HomeScreen

SETTINGS_PATH = "coc_bot/settings.json"


class ColorFormatter(logging.Formatter):
    RESET = "\x1b[0m"
    COLORS = {
        logging.DEBUG: "\x1b[36m",   # Cyan
        logging.INFO: "\x1b[90m",    # White
        logging.WARNING: "\x1b[33m", # Yellow
        logging.ERROR: "\x1b[31m",   # Red
        logging.CRITICAL: "\x1b[35m" # Magenta
    }

    def __init__(self, use_color=True):
        super().__init__("%(message)s")
        self.use_color = use_color

    def format(self, record):
        msg = record.getMessage()
        level_tag = f"[{record.levelname}]"
        if not self.use_color:
            return f"{level_tag} {msg}"
        color = self.COLORS.get(record.levelno, "")
        if color:
            level_tag = f"{color}{level_tag}{self.RESET}"
        return f"{level_tag} {msg}"

def load_settings():
    with open(SETTINGS_PATH, "r") as f:
        return json.load(f)

def save_settings(settings):
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f, indent=2)

def main():
    settings = load_settings()
    humanize = Humanize(settings)
    # Configure logging with colors when supported by terminal.
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    use_color = bool(sys.stdout.isatty())
    handler.setFormatter(ColorFormatter(use_color=use_color))
    root_logger.addHandler(handler)
    logger = logging.getLogger(__name__)

    device = bootstrap_device(settings, save_settings, logger)
    if device is None:
        return

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
        if not device.launch_game(coc_package):
            return

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
    else:
        logger.error("Failed to capture initial screen. Device may be disconnected.")
        return

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
        
        # Check home screen and perform actions
        if home_screen.is_current_screen():
            logger.info("On Home Screen. Collecting resources...")
            home_screen.collect_resources()
        else:
            logger.warning("Not on home screen, attempting recovery...")
            # Try to close popups if there are any blocking the view
            logger.debug("Closing any popups that may be blocking...")
            home_screen.close_popups()
            
        time.sleep(2)
        loop_count += 1
    
    logger.info("Test loops finished.")

if __name__ == "__main__":
    main()
