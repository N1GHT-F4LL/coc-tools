import json
import time
import cv2
import os
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
    # Instantiate device at runtime to avoid import-time side-effects.
    device = Device()
    # Optionally perform connection checks / wake here.
    try:
        device._check_connection()
    except Exception:
        pass

    ui_manager = UIManager(humanize, device)

    vision.load_assets("coc_bot/assets")

    home_screen = HomeScreen(ui_manager)
    print("\nBot starting main loop...")
    loop_count = 0
    while loop_count < 3:
        print(f"\n--- Loop {loop_count} ---")
        home_screen.close_popups()
        if home_screen.is_current_screen():
            print("On Home Screen. Collecting...")
            home_screen.collect_resources()
        else:
            print("Not on home screen, attempting recovery...")
            
        time.sleep(2)
        loop_count += 1
    
    print("Test loops finished.")

if __name__ == "__main__":
    main()
