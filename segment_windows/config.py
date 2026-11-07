from pathlib import Path

# --- File Paths ---
# Resolves to the directory containing config.py (e.g., the segment_windows folder)
BASE_DIR = Path(__file__).resolve().parent

# Defines the assets folder path. Change "assets" here if the folder name changes in the future.
ASSETS_DIR = BASE_DIR / "assets"

# Reference dimensions for dynamic scaling
REF_W, REF_H = 1024, 768

# Tesseract upscaling factor for better OCR accuracy
UPSCALE = 3

# Regions of interest defined on the 1024x768 reference frame (x0, y0, x1, y1)
ROIS = {
    "header":        (0,   0,   1024, 45),
    "params":        (745, 40,  900,  350),   # MI, Depth, SV size, Angle, ...
    "depth_scale":   (705, 35,  742,  350),   # cyan 0-4 numbers (B-mode depth, cm)
    "depth_scale_b_only":   (705, 35,  742,  640),   # full screen bmode scale
    "velocity_axis": (28,  350, 68,   640),   # -180 ... 60 (cm/s)
    "footer":        (600, 650, 900,  680),
}

# Static window coordinates for OpenCV extraction
B_MODE_Y_TOP = 54
B_MODE_Y_BOTTOM_SPLIT = 440
B_MODE_Y_BOTTOM_FULL = 830
BOTTOM_WINDOW = {'x1': 72, 'y1': 355, 'x2': 760, 'y2': 640}

CONTOUR_THRESH = 15

