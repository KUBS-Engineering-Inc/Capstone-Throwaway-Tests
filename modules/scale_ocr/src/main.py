"""Read the spectral Doppler velocity axis and the acquisition parameters by OCR.

Usage:
    python modules/scale_ocr/src/main.py [INPUT] [OUTPUT] [--no-previews]

INPUT is one of (default: all of data/scale_ocr/input/):
  - a full screenshot, a directory of them (searched recursively), or a bare
    filename inside data/scale_ocr/input/;
  - full frames plus segment_windows' windows.csv: a directory holding a
    windows.csv and the frames it names, or (as the harness passes it) a
    directory with two folders, one holding windows.csv and the other the
    frames. Only frames with a spectral window are processed.
OUTPUT is a directory (default: data/scale_ocr/output/).

Writes to OUTPUT, keyed by image:
  velocity_scale.csv  image, cm_s_per_px, cm_s_at_y0, zero_y, n_labels,
                      max_residual_cm_s, labels. The fit is
                      velocity (cm/s) = cm_s_per_px * y + cm_s_at_y0 for a
                      full-frame pixel row y; zero_y is the row of 0 cm/s.
                      cm_s_per_px is negative on a normal display and
                      positive when the spectrum is shown inverted.
                      Images whose axis can't be fitted are left out.
  params.csv          image plus each parameter-panel readout found
                      (depth_cm, heart_rate, angle_deg, ...); blank if not read.
Unless --no-previews is given, also writes a debug image per frame with the
OCR regions and the labels read. The B-mode depth scale comes from
segment_windows (windows.csv), not from this stage.
Requires the Tesseract OCR application on PATH.
"""
import argparse
import csv
import re
from pathlib import Path

import cv2
import numpy as np

from axis_reader import read_velocity_axis
from config import ASSETS_DIR, DEBUG_SUFFIX, OUTPUT_DIR, PARAM_PATTERNS, ROIS
from image_utils import scaled_roi
from params_reader import read_params

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
WINDOW = "spectral"
VELOCITY_FIELDS = ["image", "cm_s_per_px", "cm_s_at_y0", "zero_y", "n_labels",
                   "max_residual_cm_s", "labels"]
PARAM_FIELDS = ["image", *PARAM_PATTERNS]


def velocity_row(name, words, fit):
    """The velocity_scale.csv row for one image's fitted axis."""
    a, b = fit
    pts = sorted((w["cy"], int(w["text"])) for w in words if re.fullmatch(r"-?\d+", w["text"]))
    ys, vals = np.array([p[0] for p in pts]), np.array([p[1] for p in pts])
    return dict(
        image=name, cm_s_per_px=round(float(a), 5), cm_s_at_y0=round(float(b), 3),
        zero_y=round(float(-b / a), 2), n_labels=len(pts),
        max_residual_cm_s=round(float(np.abs(vals - (a * ys + b)).max()), 3),
        labels=" ".join(f"{v}@{y:.1f}" for y, v in pts),
    )


def write_debug_image(path, img, words):
    """Draw the OCR regions and the labels read over the frame."""
    dbg = img.copy()
    for name in ROIS:
        x0, y0, x1, y1 = scaled_roi(img, name)
        cv2.rectangle(dbg, (x0, y0), (x1, y1), (0, 255, 255), 1)
        cv2.putText(dbg, name, (x0, max(y0 - 3, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
    for w in words:
        x0, y0, x1, y1 = w["box"]
        cv2.rectangle(dbg, (x0, y0), (x1, y1), (0, 0, 255), 1)
        cv2.putText(dbg, w["text"], (x1 + 2, y1), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), dbg)


def list_images(path):
    """[(name, path)] for an image, or every image under a directory (name relative to it)."""
    path = Path(path)
    if path.is_file():
        return [(path.name, path)]
    if path.is_dir():
        return [(p.relative_to(path).as_posix(), p) for p in sorted(path.rglob("*"))
                if p.suffix.lower() in IMAGE_EXTS]
    raise FileNotFoundError(f"Input not found: {path}")


def find_windows(path):
    """(windows.csv, frames directory) if `path` holds segment_windows output, else None.

    Either `path` holds windows.csv next to the frames, or it holds two folders
    (the harness's layout for a node with two inputs): one with windows.csv and
    one with the frames."""
    path = Path(path)
    if not path.is_dir():
        return None
    if (path / "windows.csv").is_file():
        return path / "windows.csv", path
    found = sorted(path.glob("*/windows.csv"))
    if not found:
        return None
    others = [d for d in sorted(path.iterdir()) if d.is_dir() and d != found[0].parent]
    if len(others) != 1:
        raise ValueError(f"{path}: expected one frames folder next to {found[0].parent.name}/, found {len(others)}")
    return found[0], others[0]


def load_inputs(path):
    """[(name, image path)] to process. With segment_windows output, only the
    frames that have a spectral window; the full frame is used, not the crop."""
    windows = find_windows(path)
    if windows is None:
        return list_images(path)
    csv_path, frames_dir = windows
    with open(csv_path, newline="") as f:
        names = [r["image"] for r in csv.DictReader(f) if r["window"] == WINDOW]
    print(f"Reading {len(names)} frame(s) with a {WINDOW} window from {csv_path}, frames in {frames_dir}")
    return [(name, frames_dir / name) for name in names]


def write_csv(path, fields, rows):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, restval="")
        writer.writeheader()
        writer.writerows(rows)


def run(input, output, save_previews=True, progress=None):
    """Read the velocity axis and parameter panel of every image under `input`
    (see the module docstring for the accepted layouts) and write the CSVs (and,
    with `save_previews`, debug images) to `output`.
    `progress(done, total)`, if given, is called after each image.
    Returns the number of images whose velocity axis was fitted."""
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)
    inputs = load_inputs(input)
    velocity, params, skipped = [], [], []
    for i, (name, img_path) in enumerate(inputs):
        if progress:
            progress(i, len(inputs))
        print(f"\n=== Scale OCR: {name} ===")
        img = cv2.imread(str(img_path))
        if img is None:
            skipped.append((name, "unreadable image"))
            continue
        params.append(dict(image=name, **read_params(img)))
        words, fit = read_velocity_axis(img)
        if fit is None:
            skipped.append((name, "velocity axis: fewer than two labels read"))
        else:
            row = velocity_row(name, words, fit)
            print(f"Velocity axis: {row['cm_s_per_px']} cm/s per px, 0 cm/s at y={row['zero_y']}, "
                  f"labels {row['labels']}")
            velocity.append(row)
        if save_previews:
            write_debug_image(out_dir / f"{Path(name).with_suffix('')}{DEBUG_SUFFIX}", img, words)

    if progress:
        progress(len(inputs), len(inputs))
    write_csv(out_dir / "velocity_scale.csv", VELOCITY_FIELDS, velocity)
    write_csv(out_dir / "params.csv", PARAM_FIELDS, params)
    print(f"\nDone: fitted the velocity axis in {len(velocity)} of {len(inputs)} image(s) -> {out_dir}")
    for name, reason in skipped:
        print(f"  skipped {name}: {reason}")
    return len(velocity)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", nargs="?", default=ASSETS_DIR,
                        help="screenshot(s), frames + windows.csv, or a filename inside data/scale_ocr/input/ "
                             "(default: all of data/scale_ocr/input/)")
    parser.add_argument("output", nargs="?", default=OUTPUT_DIR,
                        help="output directory (default: data/scale_ocr/output/)")
    parser.add_argument("--no-previews", action="store_true",
                        help="only write the CSVs, not the debug images")
    args = parser.parse_args()
    input_path = Path(args.input)
    if not input_path.exists() and (ASSETS_DIR / input_path).exists():
        input_path = ASSETS_DIR / input_path  # a bare filename
    run(input_path, args.output, save_previews=not args.no_previews)


if __name__ == "__main__":
    main()
