"""Vessel pipeline: video -> frames -> (crop) -> view classification + vessel detection.

Run with:  python harness/src/main.py run harness/pipelines/vessels.py

To add a stage: give modules/<stage>/src/main.py a `run(input, output, **params)`
function, load it with load_stage("<stage>"), then add a node below with its
upstream nodes as `inputs`. List the run order with:
    python harness/src/main.py order harness/pipelines/vessels.py
"""
from pathlib import Path

from compare import files_diff
from dag import Pipeline, load_stage

ROOT = Path(__file__).resolve().parents[2]  # repo root

extract_frames = load_stage("extract_frames")

pipeline = p = Pipeline("vessels")

frames = p.node(
    "extract_frames", extract_frames.run,
    inputs=[ROOT / "data/extract_frames/input"],
    params={"fps": 1},
    compare=files_diff(),
)
