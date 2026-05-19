import re
import cv2
import logging
import numpy as np
from collections import defaultdict

logger = logging.getLogger(__name__)

_reader = None
_OCR_EARLY_EXIT_CONF = 0.92  # skip remaining variants once this confidence is reached


def _get_reader():
    global _reader
    if _reader is None:
        import warnings
        import easyocr
        # EasyOCR sets pin_memory=True in its DataLoader even when gpu=False, which
        # triggers a spurious PyTorch warning on CPU-only machines.
        warnings.filterwarnings(
            "ignore",
            message="'pin_memory' argument is set as true",
            category=UserWarning,
        )
        # EasyOCR's beam-search decoder accumulates floating-point probabilities that
        # can overflow to inf on ambiguous crops; the decoder handles inf gracefully so
        # the warning is noise.
        warnings.filterwarnings(
            "ignore",
            message="overflow encountered in scalar add",
            category=RuntimeWarning,
            module="easyocr",
        )
        logger.info("Initializing OCR reader (first use, may take ~10s)...")
        _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        logger.info("OCR reader ready.")
    return _reader


def warmup_ocr():
    """Preload OCR reader during startup to avoid first-use delay mid-cycle."""
    _get_reader()


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


def read_number_with_confidence(
    screen_bgr,
    region,
    min_value=0,
    max_value=None,
    prefer_longest=True,
    prefer_consensus=False,
):
    """Read a single integer from a BGR screen region (x1, y1, x2, y2)."""
    x1, y1, x2, y2 = region
    crop = screen_bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return None, 0.0

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
        new_cands = _extract_digit_candidates(ocr_items)
        candidates.extend(new_cands)
        # Consensus mode needs votes from multiple variants — never exit early.
        if not prefer_consensus and new_cands and max(c for _, c, _ in new_cands) >= _OCR_EARLY_EXIT_CONF:
            break

    if not candidates:
        logger.debug(f"OCR: no text in region {region}")
        return None, 0.0

    bounded = []
    for val, conf, raw in candidates:
        if val < min_value:
            continue
        if max_value is not None and val > max_value:
            continue
        bounded.append((val, conf, raw))

    if not bounded:
        logger.debug(
            f"OCR: no bounded value in region {region} (min={min_value}, max={max_value}), raw_n={len(candidates)}"
        )
        return None, 0.0
    pool = bounded
    if prefer_consensus:
        grouped = defaultdict(list)
        for val_i, conf_i, raw_i in pool:
            grouped[val_i].append((conf_i, raw_i))
        # Prefer value seen multiple times across preprocessing variants.
        # Tie-break by confidence then larger value — guards against 1↔7 misreads.
        best_val = max(
            grouped.keys(),
            key=lambda v: (len(grouped[v]), max(c for c, _ in grouped[v]), v),
        )
        conf, raw = max(grouped[best_val], key=lambda x: x[0])
        val = best_val
    elif prefer_longest:
        # Prefer longer numbers first (avoid partial reads like "46"), then confidence.
        val, conf, raw = max(pool, key=lambda x: (len(str(x[0])), x[1]))
    else:
        # For short values (e.g. dark elixir), prefer confidence first.
        val, conf, raw = max(pool, key=lambda x: (x[1], len(str(x[0]))))
    logger.debug(
        f"OCR: region {region} -> {val} (conf={conf:.3f}, raw='{raw}', n={len(pool)}, bounded={bool(bounded)})"
    )
    return val, conf
