"""Vessel pipeline: video -> frames -> (crop) -> view classification + vessel detection.

Run with:  python harness/src/main.py run harness/pipelines/vessels.py

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
detect_circular_vessels = load_stage("detect_circular_vessels")

pipeline = p = Pipeline("vessels")

frames = p.node(
    "extract_frames", extract_frames.run,
    inputs=[ROOT / "data/extract_frames/input"],
    params={"fps": 1},
    compare=files_diff(),
)

# TODO: the crop stage (full scanner screen -> B-mode view) is coming from a
# teammate. Once it exists:
#   crops = p.node("crop_view", crop_view.run, inputs=[frames], compare=files_diff())
# and use `crops` as the input of the stages below. Until then, they read the
# already-cropped sample images in data/detect_circular_vessels/input/.
vessels = p.node(
    "detect_circular_vessels", detect_circular_vessels.run,
    inputs=[ROOT / "data/detect_circular_vessels/input"],
    compare=csv_diff("detections.csv", key="image", tolerance=0.5),
)

# Same stage with the Hough-circle method, kept for comparison with the default.
vessels_hough = p.node(
    "detect_circular_vessels_hough", detect_circular_vessels.run,
    inputs=[ROOT / "data/detect_circular_vessels/input"],
    params={"method": "hough"},
    compare=csv_diff("detections.csv", key="image", tolerance=0.5),
)
