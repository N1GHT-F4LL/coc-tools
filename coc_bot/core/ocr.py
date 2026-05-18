import re
import cv2
import logging

logger = logging.getLogger(__name__)

_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        logger.info("Initializing OCR reader (first use, may take ~10s)...")
        import easyocr
        _reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        logger.info("OCR reader ready.")
    return _reader


def read_number(screen_bgr, region):
    """Read a single integer from a BGR screen region (x1, y1, x2, y2).

    Returns the parsed int, or None if no digits could be extracted.
    Upscales small crops to improve accuracy.
    """
    x1, y1, x2, y2 = region
    crop = screen_bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return None

    h, w = crop.shape[:2]
    if h < 40:
        scale = 40 / h
        crop = cv2.resize(crop, (int(w * scale), int(h * scale)),
                          interpolation=cv2.INTER_CUBIC)

    results = _get_reader().readtext(crop, detail=0, allowlist='0123456789,.')
    if not results:
        logger.debug(f"OCR: no text in region {region}")
        return None

    digits = re.sub(r'\D', '', ''.join(results).replace(',', '').replace('.', ''))
    if not digits:
        logger.debug(f"OCR: no digits from '{results}' in region {region}")
        return None

    val = int(digits)
    logger.debug(f"OCR: region {region} → {val}")
    return val
