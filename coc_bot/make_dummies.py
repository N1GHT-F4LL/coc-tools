import os
import cv2
import numpy as np

def create_dummy_images():
    paths = [
        "coc_bot/assets/ui/btn_shop.png",
        "coc_bot/assets/ui/btn_close.png",
        "coc_bot/assets/ui/btn_okay.png",
        "coc_bot/assets/buildings/icon_gold_mine_full.png",
        "coc_bot/assets/buildings/icon_elixir_collector_full.png",
        "coc_bot/assets/buildings/icon_dark_elixir_drill_full.png"
    ]
    
    for path in paths:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Create a small 50x50 black image
        img = np.zeros((50, 50, 3), dtype=np.uint8)
        cv2.imwrite(path, img)

if __name__ == "__main__":
    create_dummy_images()
    print("Dummy assets created.")