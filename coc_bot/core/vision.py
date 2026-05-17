import cv2
import numpy as np
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class Vision:
    def __init__(self):
        self.cache = {}

    def load_assets(self, asset_dir="assets"):
        logger.info(f"Loading assets from {asset_dir} into RAM cache...")
        base_path = Path(asset_dir)
        count = 0
        for path in base_path.rglob('*.png'):
            name = path.stem
            # Use both stem and relative path (namespace) as keys to avoid
            # accidental overwrites while remaining backward compatible.
            rel_key = path.relative_to(base_path).with_suffix('').as_posix()
            img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                if name not in self.cache:
                    self.cache[name] = img
                self.cache[rel_key] = img
                count += 1
        logger.info(f"Loaded {count} assets into RAM.")

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
