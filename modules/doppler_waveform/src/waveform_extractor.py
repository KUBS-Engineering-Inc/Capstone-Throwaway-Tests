"""Find the white spectral Doppler waveform and its envelope in a full Terason screenshot.
Ported from scratch/waveform.ipynb; all coordinates are full-image pixels."""
import cv2
import numpy as np

from config import MAX_INTERPOLATION_GAP, MEDIAN_KERNEL, REF_H, REF_W, ROIS, THRESHOLD


def scaled_roi(img, name):
    h, w = img.shape[:2]
    x0, y0, x1, y1 = ROIS[name]
    sx, sy = w / REF_W, h / REF_H
    return int(x0 * sx), int(y0 * sy), int(x1 * sx), int(y1 * sy)


def crop(img, name):
    x0, y0, x1, y1 = scaled_roi(img, name)
    return img[y0:y1, x0:x1], (x0, y0)


def extract_waveform(img, threshold=THRESHOLD):
    """Return Doppler mask, grayscale ROI, and foreground (x,y) pixels in IMAGE coordinates."""
    roi, (x0, y0) = crop(img, "waveform")
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    # The waveform is bright/gray, while the graph background is nearly black.
    _, mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

    # Remove isolated single-pixel speckles without erasing the thin waveform.
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_OPEN, np.ones((2, 2), dtype=np.uint8)
    )

    ys, xs = np.where(mask > 0)
    waveform_coords = np.column_stack((xs + x0, ys + y0)).astype(np.int32)
    return mask, gray, waveform_coords


def extract_envelope(mask, gray, offset, median_kernel=MEDIAN_KERNEL,
                     max_gap=MAX_INTERPOLATION_GAP):
    """Extract the intensity-weighted average y-position in original-image coordinates.

    Interpolate ONLY missing runs up to `max_gap` columns, bounded on
    BOTH sides by detected waveform pixels. Larger gaps and missing
    columns at the image edges remain NaN (not invented measurements).

    Parameters
    ----------
    mask : (H, W) uint8 binary mask of foreground Doppler pixels
    gray : (H, W) uint8 grayscale ROI matching `mask` dimensions
    offset : (x0, y0) top-left ROI offset in original image coordinates
    median_kernel : int, odd window size for median smoothing (1 to disable)
    max_gap : int, maximum missing column run length to linearly interpolate

    Returns
    -------
    envelope_coords : (W, 2) x,y image coordinates, with NaN for large gaps
    valid : (W,) True where the waveform was actually detected (not filled)
    """
    if mask.shape != gray.shape:
        raise ValueError(f"mask shape {mask.shape} does not match gray shape {gray.shape}")

    x0, y0 = offset
    _, width = mask.shape
    envelope_y = np.full(width, np.nan, dtype=float)

    for x in range(width):
        foreground_y = np.flatnonzero(mask[:, x] > 0)
        if foreground_y.size:
            weights = gray[foreground_y, x].astype(float)
            weight_sum = weights.sum()
            if weight_sum > 0:
                weighted_y = np.dot(foreground_y, weights) / weight_sum
                envelope_y[x] = weighted_y + y0

    valid = np.isfinite(envelope_y)
    if not np.any(valid):
        raise ValueError("No Doppler waveform detected: check ROI and threshold.")

    # Fill only short INTERNAL gaps. Do not extend the first/last observation.
    valid_indices = np.flatnonzero(valid)
    for left, right in zip(valid_indices[:-1], valid_indices[1:]):
        gap_length = right - left - 1
        if 0 < gap_length <= max_gap:
            envelope_y[left + 1:right] = np.linspace(
                envelope_y[left], envelope_y[right], gap_length + 2
            )[1:-1]

    # Optional median smoothing, independently within each continuous run.
    # A median filter must never smooth through a long missing (NaN) gap.
    if median_kernel > 1:
        if median_kernel % 2 != 1:
            raise ValueError("median_kernel must be odd")
        finite = np.isfinite(envelope_y)
        edges = np.diff(np.r_[False, finite, False].astype(int))
        for run_start, run_end in zip(np.flatnonzero(edges == 1),
                                      np.flatnonzero(edges == -1)):
            segment = envelope_y[run_start:run_end]
            pad = median_kernel // 2
            padded = np.pad(segment, pad, mode="edge")
            windows = np.lib.stride_tricks.sliding_window_view(padded, median_kernel)
            envelope_y[run_start:run_end] = np.median(windows, axis=1)

    envelope_x = np.arange(width) + x0
    envelope_coords = np.column_stack((envelope_x, envelope_y))
    return envelope_coords, valid
