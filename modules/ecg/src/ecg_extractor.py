"""Find the green ECG trace and its R-peak candidates in a full Terason screenshot.
Ported from scratch/ecg.ipynb; all coordinates are full-image pixels."""
import cv2
import numpy as np
from scipy.signal import find_peaks, medfilt

from config import (
    GREEN_MINUS_BLUE,
    GREEN_MINUS_RED,
    MAX_R_WIDTH,
    MEDIAN_KERNEL,
    MIN_GREEN,
    MIN_R_DISTANCE,
    MIN_R_PROMINENCE,
    MIN_R_WIDTH,
    MIN_TRACE_COVERAGE,
    REF_H,
    REF_W,
    ROIS,
)


def scaled_roi(img, name):
    h, w = img.shape[:2]
    x0, y0, x1, y1 = ROIS[name]
    sx, sy = w / REF_W, h / REF_H
    return (int(round(x0 * sx)), int(round(y0 * sy)),
            int(round(x1 * sx)), int(round(y1 * sy)))


def crop(img, name):
    x0, y0, x1, y1 = scaled_roi(img, name)
    return img[y0:y1, x0:x1], (x0, y0)


def extract_ecg(img):
    """Return ECG mask and one raw y value per x, in FULL-IMAGE pixel coordinates.

    Columns without green trace pixels remain NaN (no interpolation is performed).
    Returns (mask, coords, y, valid, coverage, ecg_present).
    """
    roi, (x0, y0) = crop(img, "ecg")
    if roi.size == 0:
        raise ValueError("ECG ROI is empty; check ROIS and image dimensions")

    b, g, r = [channel.astype(np.int16) for channel in cv2.split(roi)]
    green = ((g >= MIN_GREEN) &
             ((g - r) >= GREEN_MINUS_RED) &
             ((g - b) >= GREEN_MINUS_BLUE))
    mask = (green.astype(np.uint8) * 255)

    width = roi.shape[1]
    x_coords = x0 + np.arange(width)
    y_raw = np.full(width, np.nan, dtype=float)
    for x in range(width):
        rows = np.flatnonzero(green[:, x])
        if rows.size:
            y_raw[x] = float(np.min(rows) + y0)

    valid = np.isfinite(y_raw)
    coverage = valid.mean()

    if coverage < MIN_TRACE_COVERAGE:
        y = np.full(width, np.nan, dtype=float)
        ecg_present = False
    else:
        y = y_raw
        ecg_present = True

    coords = np.column_stack((x_coords, y))
    return mask, coords, y, valid, float(coverage), ecg_present


def detect_r_peaks(envelope_y, ecg_present, image_width):
    """Return indices of strong upward ECG spikes (small y = high on screen).

    Processes contiguous non-NaN segments independently so missing gaps
    (such as the sweep refresh bar) are never interpolated or bridged.
    """
    valid = np.isfinite(envelope_y)
    if not ecg_present or not np.any(valid):
        return np.array([], dtype=int)

    scale = image_width / REF_W
    baseline = np.nanmedian(envelope_y)
    min_prominence = MIN_R_PROMINENCE * scale
    min_distance = max(1, int(MIN_R_DISTANCE * scale))
    peak_width = (max(1, MIN_R_WIDTH * scale), max(2, MAX_R_WIDTH * scale))

    # Find contiguous segments of valid (non-NaN) data
    padded = np.concatenate(([False], valid, [False]))
    starts = np.flatnonzero(padded[1:] & ~padded[:-1])
    ends = np.flatnonzero(~padded[1:] & padded[:-1])

    refined_peaks = []

    for start, end in zip(starts, ends):
        segment = envelope_y[start:end]
        if len(segment) < MEDIAN_KERNEL:
            continue

        # Three-point median is used ONLY for detection; exported coordinates remain raw.
        smooth = medfilt(segment, kernel_size=MEDIAN_KERNEL)
        upward = baseline - smooth

        peaks, _ = find_peaks(
            upward,
            prominence=min_prominence,
            distance=min_distance,
            width=peak_width,
        )

        # Refine each detected peak using the unsmoothed ECG coordinates within the same segment
        for peak in peaks:
            left = max(0, peak - 5)
            right = min(len(segment), peak + 6)
            local_y = segment[left:right]
            refined_peaks.append(start + left + int(np.argmin(local_y)))

    return np.array(refined_peaks, dtype=int)
