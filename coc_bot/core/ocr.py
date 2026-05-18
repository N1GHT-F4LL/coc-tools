import re
import cv2
import logging
import numpy as np

logger = logging.getLogger(__name__)

_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        logger.info("Initializing OCR reader (first use, may take ~10s)...")
        import easyocr
        _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        logger.info("OCR reader ready.")
    return _reader


def _prep_variants(crop):
    """Create multiple OCR-friendly variants from the same crop."""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    gray = cv2.resize(gray, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)

    variants = [("gray", gray)]

    th_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    variants.append(("otsu", th_otsu))
    variants.append(("otsu_inv", cv2.bitwise_not(th_otsu)))

    th_adapt = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        2,
    )
    variants.append(("adapt", th_adapt))
    variants.append(("adapt_inv", cv2.bitwise_not(th_adapt)))

    kernel = np.ones((2, 2), np.uint8)
    variants.append(("otsu_close", cv2.morphologyEx(th_otsu, cv2.MORPH_CLOSE, kernel)))

    return variants


def _extract_digit_candidates(ocr_items):
    """Return parsed integer candidates from easyocr detail output."""
    out = []
    for item in ocr_items:
        if len(item) < 3:
            continue
        text = item[1] or ""
        conf = float(item[2] or 0.0)
        digits = re.sub(r"\D", "", text)
        if digits:
            out.append((int(digits), conf, text))
    return out


def read_number(
    screen_bgr,
    region,
    min_value=0,
    max_value=None,
):
    """Read a single integer from a BGR screen region (x1, y1, x2, y2)."""
    x1, y1, x2, y2 = region
    crop = screen_bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return None

    reader = _get_reader()
    prepared = _prep_variants(crop)

    candidates = []
    for _, variant in prepared:
        ocr_items = reader.readtext(
            variant,
            detail=1,
            allowlist="0123456789,.",
            paragraph=False,
            decoder="beamsearch",
            batch_size=1,
        )
        candidates.extend(_extract_digit_candidates(ocr_items))

    if not candidates:
        logger.debug(f"OCR: no text in region {region}")
        return None

    bounded = []
    for val, conf, raw in candidates:
        if val < min_value:
            continue
        if max_value is not None and val > max_value:
            continue
        bounded.append((val, conf, raw))

    pool = bounded or candidates
    # Prefer longer numbers first (avoid partial reads like "46"), then confidence.
    val, conf, raw = max(pool, key=lambda x: (len(str(x[0])), x[1]))
    logger.debug(
        f"OCR: region {region} -> {val} (conf={conf:.3f}, raw='{raw}', n={len(pool)}, bounded={bool(bounded)})"
    )
    return val
