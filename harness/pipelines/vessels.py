"""Vessel pipeline: video -> frames -> window coordinates -> vessel detection + lumen width.

    extract_frames ─► segment_windows ─► detect_circular_vessels (+ _hough)
          │                (windows.csv)  measure_diameter
          └───────────── frames ──────────┘

segment_windows writes only coordinates (windows.csv); the stages after it take
the frames and windows.csv and crop the B-mode view themselves.

Run with:  python harness/src/main.py run harness/conditions/vessels_section.json

To add a stage: give modules/<stage>/src/main.py a `run(input, output, **params)`
function, load it with load_stage("<stage>"), then add a node below with its
upstream nodes as `inputs`. List the run order with:
    python harness/src/main.py order harness/pipelines/vessels.py
"""
from pathlib import Path

from compare import csv_diff, files_diff
from dag import Pipeline, load_stage

ROOT = Path(__file__).resolve().parents[2]  # repo root

extract_frames = load_stage("extract_frames")
segment_windows = load_stage("segment_windows")
measure_diameter = load_stage("measure_diameter")
detect_circular_vessels = load_stage("detect_circular_vessels")
# A second, separate copy of the stage with its METHOD setting switched to Hough.
detect_circular_vessels_hough = load_stage("detect_circular_vessels")
detect_circular_vessels_hough.METHOD = "hough"

pipeline = p = Pipeline("vessels")

frames = p.node(
    "extract_frames", extract_frames.run,
    inputs=[ROOT / "data/extract_frames/input"],
    params={"fps": 1},
    compare=files_diff(),
)

# Coordinates only: the crops and annotated frames would be one more image per
# window per frame. Set "save_images": true in a conditions file to inspect them.
windows = p.node(
    "segment_windows", segment_windows.run,
    inputs=[frames],
    params={"save_images": False},
    compare=csv_diff("windows.csv", key=("image", "window")),
)

# The stages below get a directory with extract_frames/ and segment_windows/ in
# it, and crop each frame to its B-mode window from windows.csv.
vessels = p.node(
    "detect_circular_vessels", detect_circular_vessels.run,
    inputs=[frames, windows],
    compare=csv_diff("detections.csv", key="image", tolerance=0.5),
)

# Same stage with the Hough-circle method, kept for comparison with the default.
vessels_hough = p.node(
    "detect_circular_vessels_hough", detect_circular_vessels_hough.run,
    inputs=[frames, windows],
    compare=csv_diff("detections.csv", key="image", tolerance=0.5),
)

# Lumen width at the Doppler cursor. Frames without a cursor (e.g. B-only) are skipped.
diameters = p.node(
    "measure_diameter", measure_diameter.run,
    inputs=[frames, windows],
    params={"save_previews": False},
    compare=csv_diff("diameters.csv", key="image", tolerance=0.5),
)
