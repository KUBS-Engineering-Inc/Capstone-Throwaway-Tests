from pathlib import Path
DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "segment_windows"  # modules/segment_windows/src/config.py -> repo root
ASSETS_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"

# These fixed coordinates are based on the expected screenshot dimensions.
# Coordinates are written as (left, top, right, bottom)
FRAME_WIDTH = 1024
FRAME_HEIGHT = 768

# OCR reads the footer to identify the active mode.
FOOTER_ROI = (600, 650, 900, 680)

# OCR reads right-hand parameter panel that displays the active B-mode depth..
DEPTH_LABEL_ROI = (745, 170, 900, 205)

# Bounds of the visible spectral plotting area in the sample frames. The box
# includes its border and excludes the velocity labels to the left of the plot.
SPECTRAL_WINDOW = (74, 355, 753, 642)

# Fixed vertical bounds follow the top and bottom depth-scale ticks. The bottom
# tick is at a different row in split and B-only layouts.
B_MODE_TOP_TICK = 50
B_MODE_SPLIT_BOTTOM_TICK = 338
B_MODE_FULL_BOTTOM_TICK = 632
B_MODE_TOP_DEPTH_CM = 0.0

# Search for B-mode between the scale and the ultrasound area, including the
# full scale tick length (through x=759) but stopping before parameter text.
B_MODE_SEARCH_LEFT = 80
B_MODE_SEARCH_TOP = B_MODE_TOP_TICK
B_MODE_SEARCH_RIGHT = 760
B_MODE_SPLIT_BOTTOM = B_MODE_SPLIT_BOTTOM_TICK + 1
B_MODE_FULL_BOTTOM = B_MODE_FULL_BOTTOM_TICK + 1

# TUNABLE: OCR works on small text more reliably when its input is enlarged.
OCR_UPSCALE = 3

# TUNABLE: Grayscale pixels strictly brighter than this cutoff become white for contour detection; darker pixels become black.
CONTOUR_THRESHOLD = 15

# Both tunable values are worth experimenting with in the future. The current values work for the sample frames.
