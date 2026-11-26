"""Where a run's results live, and the per-frame layout.

Stage layout (the default): one folder per node, named <step>_<node>, holding
what the stage wrote and its log.txt:

    runs/<id>/01_extract_frames/  02_segment_windows/  03_ecg/  ...

Frame layout: after the run, every node's results are split up by frame:

    runs/<id>/frames/<video>/<frame>/<step>_<node>/   that frame's files and CSV rows
    runs/<id>/shared/<step>_<node>/                   results not tied to one frame
    runs/<id>/logs/<step>_<node>.txt

A frame is an image written by a source node (one with no upstream node, e.g.
extract_frames), keyed by its path relative to that node's folder
("recording_oct_5/frame_001800.jpg"). For each node:
  - a CSV with an `image` column is split by that column: each frame gets the
    rows whose `image` is its key, under the CSV's own relative path. Rows for
    no known frame, and CSVs with no rows at all, go to shared/.
  - any other file goes to the frame it is named after: a file in the frame's
    directory whose name contains the frame's stem as a whole `_`-separated
    part ("frame_001800_ecg_overlay.png", "annotated_frame_001800.jpg").
    Other files go to shared/.
assemble_stage() reverses this, so a run in either layout can be compared
against a run in the other.
"""
import csv
import shutil
from collections import defaultdict
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
LOG_NAME = "log.txt"
FRAMES, SHARED, LOGS = "frames", "shared", "logs"


def stage_dir(run_dir, name):
    """The folder holding node `name`'s results in a stage-layout run: <step>_<name>/,
    or <name>/output/ in runs made before that layout. None if neither exists."""
    run_dir = Path(run_dir)
    found = sorted(p for p in run_dir.glob(f"[0-9][0-9]_{name}") if p.is_dir())
    if found:
        return found[0]
    legacy = run_dir / name / "output"
    return legacy if legacy.is_dir() else None


def is_frame_layout(run_dir):
    return (Path(run_dir) / FRAMES).is_dir()


def _image_column(path):
    """The CSV's header if it has an `image` column, else None."""
    with open(path, newline="") as f:
        header = next(csv.reader(f), None)
    return header if header and "image" in header else None


def _write_rows(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _frame_for(rel, frames_by_dir):
    """The frame key a non-CSV file belongs to, or None. `frames_by_dir` maps
    a directory (relative path) to {frame stem: frame key}."""
    stems = frames_by_dir.get(rel.parent.as_posix())
    if not stems:
        return None
    parts = rel.name.replace(".", "_").split("_")
    best = None
    for i in range(len(parts)):
        for j in range(i + 1, len(parts) + 1):
            stem = "_".join(parts[i:j])
            if stem in stems and (best is None or len(stem) > len(best)):
                best = stem
    return stems[best] if best else None


def frame_keys(source_dirs):
    """Every image under the source nodes' folders, as relative POSIX paths."""
    keys = []
    for d in source_dirs:
        keys += [p.relative_to(d).as_posix() for p in sorted(Path(d).rglob("*"))
                 if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    return sorted(set(keys))


def split_by_frame(run_dir, stage_dirs, keys):
    """Move every stage folder's results into frames/ and shared/ (see the
    module docstring), then remove the stage folders. `stage_dirs` maps a
    folder name (<step>_<node>) to its path; `keys` are the frame keys.
    Each stage's log.txt goes to logs/<step>_<node>.txt."""
    run_dir = Path(run_dir)
    key_set = set(keys)
    frames_by_dir = defaultdict(dict)
    for key in keys:
        k = Path(key)
        frames_by_dir[k.parent.as_posix()][k.stem] = key

    def frame_folder(key):
        return run_dir / FRAMES / Path(key).with_suffix("")

    for key in keys:
        frame_folder(key).mkdir(parents=True, exist_ok=True)

    for folder, src in stage_dirs.items():
        if not src.is_dir():
            continue
        log = src / LOG_NAME
        if log.is_file():
            (run_dir / LOGS).mkdir(exist_ok=True)
            shutil.move(log, run_dir / LOGS / f"{folder}.txt")
        for path in sorted(p for p in src.rglob("*") if p.is_file()):
            rel = path.relative_to(src)
            fields = _image_column(path) if path.suffix.lower() == ".csv" else None
            if fields:
                by_frame = defaultdict(list)
                with open(path, newline="") as f:
                    for row in csv.DictReader(f):
                        by_frame[row["image"] if row["image"] in key_set else None].append(row)
                for key, rows in by_frame.items():
                    if key is not None:
                        _write_rows(frame_folder(key) / folder / rel, fields, rows)
                if by_frame.get(None) or not by_frame:
                    _write_rows(run_dir / SHARED / folder / rel, fields, by_frame.get(None, []))
                path.unlink()
                continue
            key = _frame_for(rel, frames_by_dir)
            dest = frame_folder(key) / folder / rel.name if key else run_dir / SHARED / folder / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(path, dest)
        shutil.rmtree(src)


def assemble_stage(run_dir, name, dest):
    """Rebuild node `name`'s stage folder from a frame-layout run into `dest`
    (CSV rows in frame order, then shared rows). Returns `dest`, or None if the
    run has nothing for that node."""
    run_dir, dest = Path(run_dir), Path(dest)
    found = False
    csv_rows = {}  # relative path -> (fields, rows)

    def add(path, rel, frame_parent):
        nonlocal found
        found = True
        fields = _image_column(path) if path.suffix.lower() == ".csv" else None
        if fields:
            with open(path, newline="") as f:
                csv_rows.setdefault(rel.as_posix(), (fields, []))[1].extend(csv.DictReader(f))
            return
        target = dest / (frame_parent / rel.name if frame_parent is not None else rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)

    frames_root = run_dir / FRAMES
    for stage in sorted(frames_root.glob(f"**/[0-9][0-9]_{name}")):
        if not stage.is_dir():
            continue
        frame_parent = stage.parent.relative_to(frames_root).parent  # <video>
        for path in sorted(p for p in stage.rglob("*") if p.is_file()):
            add(path, path.relative_to(stage), frame_parent)
    for stage in sorted((run_dir / SHARED).glob(f"[0-9][0-9]_{name}")):
        for path in sorted(p for p in stage.rglob("*") if p.is_file()):
            add(path, path.relative_to(stage), None)
    for rel, (fields, rows) in csv_rows.items():
        _write_rows(dest / rel, fields, rows)
    return dest if found else None
