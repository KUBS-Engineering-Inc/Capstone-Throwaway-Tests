"""Read a numeric axis (tick labels) and fit value = a * pixel_y + b.
Ported from scale_ocr/test_ocr.ipynb."""
import re

import numpy as np
import pytesseract

from config import BORDER, OUTLIER_TOLERANCE_PX, REF_H, UPSCALE, VELOCITY_WHITELIST
from image_utils import crop, prep_light_on_dark, scaled_roi


def ocr_words(prepped, offset, psm=11, whitelist=None):
    """Return [{text, conf, cx, cy, box}] with coords in ORIGINAL image pixels."""
    cfg = f"--oem 3 --psm {psm}"
    if whitelist:
        cfg += f" -c tessedit_char_whitelist={whitelist}"
    data = pytesseract.image_to_data(prepped, config=cfg, output_type=pytesseract.Output.DICT)

    ox, oy = offset
    words = []
    for i, txt in enumerate(data["text"]):
        txt = txt.strip()
        if whitelist:
            # The axis tick mark right after a label gets read as a trailing '-'
            # ("-180-", "30-"), which breaks number matching. Strip it.
            txt = txt.rstrip("-")
            if not re.search(r"\d", txt):
                continue
        if not txt or float(data["conf"][i]) < 0:
            continue
        x, y = data["left"][i] - BORDER, data["top"][i] - BORDER
        w, h = data["width"][i], data["height"][i]
        x0, y0 = ox + x / UPSCALE, oy + y / UPSCALE
        x1, y1 = x0 + w / UPSCALE, y0 + h / UPSCALE
        words.append({
            "text": txt,
            "conf": float(data["conf"][i]),
            "cx": (x0 + x1) / 2,
            "cy": (y0 + y1) / 2,
            "box": (int(x0), int(y0), int(x1), int(y1)),
        })
    return words


def ocr_words_multi(prepped, offset, psms=(11, 6, 12), whitelist=None):
    """Run several Tesseract page-segmentation modes and keep the most confident
    reading at each location. Isolated single characters (like a lone '0') are
    often missed by one mode but caught by another."""
    allw = []
    for p in psms:
        allw += ocr_words(prepped, offset, psm=p, whitelist=whitelist)
    allw.sort(key=lambda w: -w["conf"])
    kept = []
    for w in allw:
        if not any(abs(w["cy"] - k["cy"]) < 6 and abs(w["cx"] - k["cx"]) < 15 for k in kept):
            kept.append(w)
    return kept


def fit_axis(words, label, verbose=True):
    """Linear fit value = a * pixel_y + b from numeric tick labels."""
    pts = []
    for w in words:
        m = re.fullmatch(r"-?\d+", w["text"])
        if m:
            pts.append((w["cy"], int(w["text"])))
    if len(pts) < 2:
        print(f"[{label}] not enough numeric labels found: {pts}")
        return None
    ys, vals = zip(*pts)
    a, b = np.polyfit(ys, vals, 1)
    resid = np.abs(np.array(vals) - (a * np.array(ys) + b)).max()
    if verbose:
        print(f"[{label}] labels (y_px, value): {sorted(pts)}")
        print(f"[{label}] value = {a:.4f} * y + {b:.2f}   (max residual {resid:.2f})")
        print(f"[{label}] -> {abs(1 / a):.3f} px per unit")
    return a, b


def recover_missing(img, words, fit, roi_name, prep_fn, whitelist, label, must_include=()):
    """Labels are evenly spaced, so use the fit to predict where a missing label
    should be, then re-OCR just a thin strip around that spot."""
    a, b = fit
    found = {int(w["text"]) for w in words if re.fullmatch(r"-?\d+", w["text"])}
    if len(found) < 2:
        return words, fit
    vals = sorted(found)
    step = int(np.gcd.reduce(np.diff(vals))) or 1
    expected = set(range(vals[0], vals[-1] + 1, step)) | set(must_include)

    x0, _, x1, _ = scaled_roi(img, roi_name)
    h = img.shape[0]
    half = 12 * h / REF_H
    for v in sorted(expected - found):
        cy = (v - b) / a
        ya, yb = int(cy - half), int(cy + half)
        if ya < 0 or yb > h:
            print(f"[{label}] {v} is predicted off-image (y={cy:.0f}px)")
            continue
        strip = prep_fn(img[ya:yb, x0:x1])
        hit = []
        for psm in (7, 8, 10):  # single line, single word, single character
            new = ocr_words(strip, (x0, ya), psm=psm, whitelist=whitelist)
            hit = [w for w in new if w["text"] == str(v)]
            if hit:
                break
        if hit:
            words.append(hit[0])
            print(f"[{label}] recovered missing label {v} near y={cy:.0f}px")
        else:
            print(f"[{label}] {v} still not read; fit predicts it at y={cy:.0f}px "
                  f"(it will still be correct on the fitted scale)")
    return words, fit_axis(words, label)


def reject_outliers(words, tol_px=OUTLIER_TOLERANCE_PX):
    """Tick labels are linearly spaced, so drop any reading that sits off the fitted
    line (e.g. a '0' misread as '6'). Removes the worst point and refits until
    every remaining label is within tol_px pixels of the line."""
    words = [w for w in words if re.fullmatch(r"-?\d+", w["text"])]
    while len(words) > 3:
        ys = np.array([w["cy"] for w in words])
        vals = np.array([int(w["text"]) for w in words])
        a, b = np.polyfit(ys, vals, 1)
        resid_px = np.abs((vals - b) / a - ys)
        worst = int(resid_px.argmax())
        if resid_px[worst] <= tol_px:
            break
        print(f"  dropping outlier label {words[worst]['text']!r} at y={ys[worst]:.0f}px "
              f"({resid_px[worst]:.1f}px off the fit)")
        words.pop(worst)
    return words


def read_axis(img, roi_name, prep_fn, whitelist, label, must_include=()):
    """Return (words, fit): the tick labels read and value = a * y + b, or None."""
    roi, off = crop(img, roi_name)
    words = ocr_words_multi(prep_fn(roi), off, whitelist=whitelist)
    words = reject_outliers(words)
    fit = fit_axis(words, label, verbose=False)
    if fit:
        return recover_missing(img, words, fit, roi_name, prep_fn, whitelist, label, must_include)
    return words, fit


def read_velocity_axis(img):
    """Read the spectral Doppler velocity axis (cm/s) on the left of the screen."""
    return read_axis(img, "velocity_axis", prep_light_on_dark, VELOCITY_WHITELIST,
                     "velocity (cm/s)", must_include=[0])
