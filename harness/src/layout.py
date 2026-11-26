"""Where a run's results live.

Stage layout: one folder per node, named <step>_<node>, holding what the stage
wrote and its log.txt:

    runs/<id>/01_extract_frames/  02_segment_windows/  03_ecg/  ...
"""
from pathlib import Path

LOG_NAME = "log.txt"


def stage_dir(run_dir, name):
    """The folder holding node `name`'s results in a stage-layout run: <step>_<name>/,
    or <name>/output/ in runs made before that layout. None if neither exists."""
    run_dir = Path(run_dir)
    found = sorted(p for p in run_dir.glob(f"[0-9][0-9]_{name}") if p.is_dir())
    if found:
        return found[0]
    legacy = run_dir / name / "output"
    return legacy if legacy.is_dir() else None
