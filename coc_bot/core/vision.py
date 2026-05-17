import cv2
import numpy as np
import os
from pathlib import Path

class Vision:
    def __init__(self):
        self.cache = {}

    def load_assets(self, asset_dir="assets"):
        print(f"Loading assets from {asset_dir} into RAM cache...")
        base_path = Path(asset_dir)
        count = 0
        for path in base_path.rglob('*.png'):
            name = path.stem
            img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                self.cache[name] = img
                count += 1
        print(f"Loaded {count} assets into RAM.")

    def find_template(self, screen_color, template_name, threshold=0.7):
        if template_name not in self.cache or screen_color is None:
            return None
            
        template = self.cache[template_name]
        screen_gray = cv2.cvtColor(screen_color, cv2.COLOR_BGR2GRAY)
        
        # Fast template matching (Assumes exact resolution match)
        res = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        
        if max_val >= threshold:
            h, w = template.shape[:2]
            return (max_loc[0] + w // 2, max_loc[1] + h // 2)
            
        return None

vision = Vision()
