from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "doppler_waveform"  # modules/doppler_waveform/src/config.py -> repo root
ASSETS_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"

# Image ROIs use the same (x0, y0, x1, y1) format as test_ocr.
# The Doppler ROI is limited to the WHITE spectral waveform.
# It excludes the ECG at the bottom and the horizontal zero-velocity line.
# Adjust these values if the Terason layout changes.
REF_W, REF_H = 1024, 768
ROIS = {
    "waveform": (85, 420, 697, 556),
}

THRESHOLD = 20  # brightness cutoff, 0-255; tune for different captures
MEDIAN_KERNEL = 1   # odd window width, smooths the extracted upper edge (1 = off)
MAX_INTERPOLATION_GAP = 5  # only fill missing runs of at most 5 columns

MASK_SUFFIX = "_waveform_mask.png"
OVERLAY_SUFFIX = "_envelope_overlay.png"
