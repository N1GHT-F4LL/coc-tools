import cv2
import numpy as np
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Initialize ORB detector once (reuse across calls for efficiency)
ORB_DETECTOR = cv2.ORB_create(nfeatures=500, scaleFactor=1.2, nlevels=8)

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
        
        # Fallback: ORB feature matching for scale/rotation robustness
        logger.debug(f"Template match confidence {max_val:.3f} < {threshold}; trying ORB fallback for '{template_name}'")
        orb_match = self._find_by_orb_features(screen_gray, template, template_name)
        if orb_match:
            return orb_match
            
        return None

    def _find_by_orb_features(self, screen_gray, template, template_name, min_matches=4):
        """
        Fallback feature matching using ORB and FLANN.
        Robust to scale and rotation changes.
        """
        try:
            # Detect keypoints and descriptors
            kp_tmpl, desc_tmpl = ORB_DETECTOR.detectAndCompute(template, None)
            kp_screen, desc_screen = ORB_DETECTOR.detectAndCompute(screen_gray, None)

            if desc_tmpl is None or desc_screen is None or len(kp_tmpl) < 4 or len(kp_screen) < 4:
                logger.debug(f"Not enough features in template or screen for '{template_name}'")
                return None

            # Use FLANN matcher for quick matching
            FLANN_INDEX_LSH = 6
            index_params = dict(algorithm=FLANN_INDEX_LSH, table_number=12, key_size=20, multi_probe_level=2)
            search_params = dict(checks=50)
            flann = cv2.FlannBasedMatcher(index_params, search_params)

            # knnMatch for better results
            matches = flann.knnMatch(desc_tmpl, desc_screen, k=2)
            
            # Lowe's ratio test to filter good matches
            good_matches = []
            for match_pair in matches:
                if len(match_pair) == 2:
                    m, n = match_pair
                    if m.distance < 0.7 * n.distance:
                        good_matches.append(m)

            if len(good_matches) < min_matches:
                logger.debug(f"ORB fallback: only {len(good_matches)}/{min_matches} good matches for '{template_name}'")
                return None

            # Compute homography and estimate template center in screen
            tmpl_pts = np.float32([kp_tmpl[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
            screen_pts = np.float32([kp_screen[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

            H, mask = cv2.findHomography(tmpl_pts, screen_pts, cv2.RANSAC, 5.0)
            if H is None:
                logger.debug(f"ORB fallback: homography not found for '{template_name}'")
                return None

            # Project template corners to screen space
            h, w = template.shape[:2]
            tmpl_corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
            screen_corners = cv2.perspectiveTransform(tmpl_corners, H)
            
            # Compute center of matched region
            center = np.mean(screen_corners, axis=0).flatten()
            center_x, center_y = int(center[0]), int(center[1])
            
            logger.info(f"ORB fallback matched '{template_name}' at ({center_x}, {center_y}) with {len(good_matches)} features")
            return (center_x, center_y)

        except Exception as e:
            logger.debug(f"ORB fallback failed for '{template_name}': {e}")
            return None

vision = Vision()
