"""Read the acquisition parameters from the right-hand panel.
Ported from scale_ocr/test_ocr.ipynb."""
import re

import pytesseract

from config import PARAM_PATTERNS
from image_utils import crop, prep_light_on_dark


def read_params(img):
    """Return {name: value} for each PARAM_PATTERNS readout found in the panel."""
    roi, _ = crop(img, "params")
    text = pytesseract.image_to_string(prep_light_on_dark(roi), config="--oem 3 --psm 6")
    print("\n--- raw parameter text ---")
    print(text)

    out = {}
    for key, pat in PARAM_PATTERNS.items():
        m = re.search(pat, text, flags=re.I)
        if m:
            out[key] = float(m.group(1))
    return out
