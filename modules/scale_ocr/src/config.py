from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "scale_ocr"  # modules/scale_ocr/src/config.py -> repo root
ASSETS_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"

# ---------------------------------------------------------------------------
# Regions of interest, defined on a 1024x768 reference frame (x0, y0, x1, y1).
# They are rescaled automatically if your frames are a different size.
# The B-mode depth scale is read by segment_windows, not here.
# ---------------------------------------------------------------------------
REF_W, REF_H = 1024, 768
ROIS = {
    "params":        (745, 40,  900,  350),   # MI, Depth, SV size, Angle, ...
    "velocity_axis": (28,  350, 68,   640),   # -180 ... 60 (cm/s)
}

UPSCALE = 3  # Tesseract does much better on larger text
BORDER = 10  # white padding added around a prepped crop, in upscaled pixels

VELOCITY_WHITELIST = "-0123456789"
OUTLIER_TOLERANCE_PX = 3.0  # a tick label further than this from the fitted line is dropped

# Parameter-panel readouts: name -> regex whose first group is the number.
PARAM_PATTERNS = {
    "depth_cm":    r"Depth\s*([\d.]+)\s*cm",
    "frame_rate":  r"([\d.]+)\s*Hz",
    "heart_rate":  r"([\d.]+)\s*bpm",
    "sv_size_mm":  r"SV\s*size\s*([\d.]+)\s*mm",
    "sv_depth_cm": r"SV\s*dep\s*([\d.]+)\s*cm",
    "freq_mhz":    r"Freq\s*([\d.]+)\s*MHz",
    "prf_khz":     r"PRF\s*([\d.]+)\s*kHz",
    "angle_deg":   r"Angle\s*(\d+)",
    "mi":          r"MI\s*([\d.]+)",
}

DEBUG_SUFFIX = "_ocr_debug.png"
