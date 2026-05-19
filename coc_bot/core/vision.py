import cv2
import numpy as np
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

ORB_DETECTOR = cv2.ORB_create(nfeatures=500, scaleFactor=1.2, nlevels=8)

# Native scale first so a perfect-resolution match exits early; the spread
# covers typical emulator resolution mismatches (720p/900p/1080p).
DEFAULT_MATCH_SCALES = (1.0, 0.75, 1.25, 0.5, 1.5, 0.6, 0.85)


class Vision:
    def __init__(self):
        self.cache = {}

    def load_assets(self, asset_dir="assets"):
        logger.info(f"Loading assets from {asset_dir} into RAM cache...")
        base_path = Path(asset_dir)
        count = 0
        for path in base_path.rglob('*.png'):
            name = path.stem
            # Store under both stem and rel-path key so basenames that collide
            # across subdirs can still be addressed unambiguously (§11.5).
            rel_key = path.relative_to(base_path).with_suffix('').as_posix()
            img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                if name not in self.cache:
                    self.cache[name] = img
                self.cache[rel_key] = img
                count += 1
        logger.info(f"Loaded {count} assets into RAM.")

    def _find_best_scale(self, screen_gray, template, threshold, scales=None):
        """Try each scale; return (best_val, best_scaled, result_map) or (best_val, None, None) if below threshold."""
        if scales is None:
            scales = DEFAULT_MATCH_SCALES
        th, tw = template.shape[:2]
        sh, sw = screen_gray.shape[:2]

        best_val = -1.0
        best_scaled = None
        best_result_map = None

        for s in scales:
            nh, nw = int(th * s), int(tw * s)
            if nh < 8 or nw < 8 or nh > sh or nw > sw:
                continue
            scaled = template if s == 1.0 else cv2.resize(
                template, (nw, nh),
                interpolation=cv2.INTER_AREA if s < 1.0 else cv2.INTER_CUBIC,
            )
            result_map = cv2.matchTemplate(screen_gray, scaled, cv2.TM_CCOEFF_NORMED)
            _, mv, _, _ = cv2.minMaxLoc(result_map)
            if mv > best_val:
                best_val = mv
                best_scaled = scaled
                best_result_map = result_map
            # Strong native-scale hit: no need to scan further scales.
            if s == 1.0 and mv >= threshold:
                break

        return best_val, best_scaled, best_result_map

    def find_template(self, screen_color, template_name, threshold=0.7, use_orb_fallback=True, scales=None):
        if template_name not in self.cache or screen_color is None:
            return None

        template = self.cache[template_name]
        screen_gray = cv2.cvtColor(screen_color, cv2.COLOR_BGR2GRAY)

        best_val, best_scaled, result_map = self._find_best_scale(
            screen_gray, template, threshold, scales
        )

        if result_map is not None and best_val >= threshold:
            _, _, _, max_loc = cv2.minMaxLoc(result_map)
            bh, bw = best_scaled.shape[:2]
            return (max_loc[0] + bw // 2, max_loc[1] + bh // 2)

        if use_orb_fallback:
            logger.debug(
                f"Template match best confidence {best_val:.3f} < {threshold}; "
                f"trying ORB fallback for '{template_name}'"
            )
            orb_match = self._find_by_orb_features(screen_gray, template, template_name)
            if orb_match:
                return orb_match

        return None

    def find_all_matches(self, screen_color, template_name, threshold=0.7, min_distance=40):
        """Return (cx, cy) centers for all non-overlapping matches above threshold (NMS)."""
        if template_name not in self.cache or screen_color is None:
            return []

        template = self.cache[template_name]
        screen_gray = cv2.cvtColor(screen_color, cv2.COLOR_BGR2GRAY)

        best_val, best_scaled, result_map = self._find_best_scale(
            screen_gray, template, threshold
        )
        if result_map is None or best_val < threshold:
            return []

        bh, bw = best_scaled.shape[:2]
        result_map = result_map.copy()  # NMS zeroes regions in-place

        locations = []
        while True:
            _, max_val, _, max_loc = cv2.minMaxLoc(result_map)
            if max_val < threshold:
                break
            x, y = max_loc
            locations.append((x + bw // 2, y + bh // 2))
            x1 = max(0, x - min_distance)
            y1 = max(0, y - min_distance)
            x2 = min(result_map.shape[1], x + bw + min_distance)
            y2 = min(result_map.shape[0], y + bh + min_distance)
            result_map[y1:y2, x1:x2] = 0.0

        return locations

    def _find_by_orb_features(self, screen_gray, template, template_name, min_matches=4):
        """Fallback feature matching using ORB and FLANN. Robust to scale/rotation."""
        try:
            kp_tmpl, desc_tmpl = ORB_DETECTOR.detectAndCompute(template, None)
            kp_screen, desc_screen = ORB_DETECTOR.detectAndCompute(screen_gray, None)

            if desc_tmpl is None or desc_screen is None or len(kp_tmpl) < 4 or len(kp_screen) < 4:
                logger.debug(f"Not enough features in template or screen for '{template_name}'")
                return None

            index_params = dict(algorithm=6, table_number=12, key_size=20, multi_probe_level=2)
            flann = cv2.FlannBasedMatcher(index_params, dict(checks=50))
            matches = flann.knnMatch(desc_tmpl, desc_screen, k=2)

            good_matches = [
                m for pair in matches if len(pair) == 2
                for m, n in [pair] if m.distance < 0.7 * n.distance
            ]
            if len(good_matches) < min_matches:
                logger.debug(f"ORB fallback: only {len(good_matches)}/{min_matches} good matches for '{template_name}'")
                return None

            tmpl_pts = np.float32([kp_tmpl[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
            screen_pts = np.float32([kp_screen[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

            H, _ = cv2.findHomography(tmpl_pts, screen_pts, cv2.RANSAC, 5.0)
            if H is None:
                logger.debug(f"ORB fallback: homography not found for '{template_name}'")
                return None

            h, w = template.shape[:2]
            corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
            center = np.mean(cv2.perspectiveTransform(corners, H), axis=0).flatten()
            cx, cy = int(center[0]), int(center[1])
            logger.debug(f"ORB fallback matched '{template_name}' at ({cx}, {cy}) with {len(good_matches)} features")
            return (cx, cy)

        except Exception as e:
            logger.debug(f"ORB fallback failed for '{template_name}': {e}")
            return None


vision = Vision()
