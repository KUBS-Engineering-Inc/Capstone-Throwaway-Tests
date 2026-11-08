"""Vessel pipeline: video -> frames -> (crop) -> view classification + vessel detection.

Run with:  harness run harness/pipelines/vessels.py

To add a stage: give it a `run(input, output, **params)` function, install it
into the shared venv (add `-e ./<stage>` to requirements.txt), then add a node
below with its upstream nodes as `inputs`.
"""
from pathlib import Path

import extract_frames

from harness import Pipeline, files_diff

ROOT = Path(__file__).resolve().parents[2]  # repo root

pipeline = p = Pipeline("vessels")

frames = p.node(
    "extract_frames", extract_frames.run,
    inputs=[ROOT / "extract_frames/input"],
    params={"fps": 1},
    compare=files_diff(),
)
