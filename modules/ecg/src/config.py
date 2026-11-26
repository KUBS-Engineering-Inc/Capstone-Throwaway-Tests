from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "ecg"  # modules/ecg/src/config.py -> repo root
ASSETS_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"

# Coordinate conventions match test_ocr and the waveform extraction notebook.
# Reference resolution: 1024 x 768; ROI: (x0, y0, x1, y1).
# The selected region covers the green ECG line, not the white Doppler signal.
REF_W, REF_H = 1024, 768
ROIS = {
    "ecg": (80, 589, 716, 643),
}

# Green detection: require green dominance rather than overall brightness.
MIN_GREEN = 45
GREEN_MINUS_RED = 22
GREEN_MINUS_BLUE = 16

# Conservative safeguards against spurious peak detections.
MIN_TRACE_COVERAGE = 0.70     # fraction of columns containing ECG-colored pixels
MIN_PRESENT_PEAKS = 2        # avoid declaring an ECG from one isolated green spike
MIN_R_PROMINENCE = 18        # minimum peak height relative to nearby ECG (pixels)
MIN_R_DISTANCE = 75         # minimum separation on THIS 1024px reference image
MIN_R_WIDTH, MAX_R_WIDTH = 1.5, 18   # narrow QRS-like peak in pixels
MEDIAN_KERNEL = 3           # small filtering of y-series for detecting peaks only

OVERLAY_SUFFIX = "_ecg_overlay.png"
GRAPH_SUFFIX = "_ecg_graph.png"
MASK_SUFFIX = "_ecg_mask.png"
