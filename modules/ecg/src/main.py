"""Extract the green ECG trace and R-peak candidates from spectral Doppler screens.

Usage:
    python modules/ecg/src/main.py [INPUT] [OUTPUT] [--no-previews]

INPUT is one of (default: all of data/ecg/input/):
  - a full screenshot, a directory of them (searched recursively), or a bare
    filename inside data/ecg/input/;
  - full frames plus segment_windows' windows.csv: a directory holding a
    windows.csv and the frames it names, or (as the harness passes it) a
    directory with two folders, one holding windows.csv and the other the
    frames. Only frames with a spectral window are processed.
OUTPUT is a directory (default: data/ecg/output/).

Writes to OUTPUT, keyed by image:
  ecg_summary.csv  image, ecg_present, coverage, n_r_peaks
  ecg_trace.csv    image, x, y: one row per column of the ECG region; y is
                   blank where no trace was found (gaps are not interpolated)
  r_peaks.csv      image, x, y: one row per R-peak candidate
Coordinates are full-frame pixels (origin top left). Unless --no-previews is
given, also writes the ECG mask, overlay and graph per image.
The ECG region is a fixed rectangle on the 1024x768 Terason layout.
"""
import argparse
import csv
from pathlib import Path

import cv2
import numpy as np

from config import ASSETS_DIR, OUTPUT_DIR
from ecg_extractor import detect_r_peaks, extract_ecg
from previews import write_previews

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
WINDOW = "spectral"


def analyze(img):
    """Return the ECG trace and R-peak candidates of one full screenshot."""
    mask, coords, ecg_y, valid, coverage, present = extract_ecg(img)
    peaks = detect_r_peaks(ecg_y, present, image_width=img.shape[1])
    return dict(
        mask=mask, coords=coords, ecg_y=ecg_y, valid_columns=valid,
        coverage=coverage, ecg_present=present,
        r_peaks_x=coords[peaks, 0].astype(int), r_peaks_y=ecg_y[peaks],
    )


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


def _fmt(value):
    return "" if not np.isfinite(value) else round(float(value), 3)


def write_csv(path, fields, rows):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(input, output, save_previews=True, progress=None):
    """Extract the ECG from every image under `input` (see the module docstring
    for the accepted layouts) and write the CSVs (and, with `save_previews`,
    diagnostic images) to `output`.
    `progress(done, total)`, if given, is called after each image.
    Returns the number of images processed."""
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)
    inputs = load_inputs(input)
    summary, trace, peaks, skipped = [], [], [], []
    for i, (name, img_path) in enumerate(inputs):
        if progress:
            progress(i, len(inputs))
        print(f"\n=== ECG: {name} ===")
        img = cv2.imread(str(img_path))
        if img is None:
            skipped.append((name, "unreadable image"))
            continue
        try:
            r = analyze(img)
        except ValueError as e:
            skipped.append((name, str(e)))
            continue
        print(f"Coverage {r['coverage']:.2f}, ECG present: {r['ecg_present']}, "
              f"R-peak candidates: {len(r['r_peaks_x'])}")
        summary.append(dict(image=name, ecg_present=r["ecg_present"],
                            coverage=round(r["coverage"], 4), n_r_peaks=len(r["r_peaks_x"])))
        trace += [dict(image=name, x=int(x), y=_fmt(y)) for x, y in zip(r["coords"][:, 0], r["ecg_y"])]
        peaks += [dict(image=name, x=int(x), y=_fmt(y)) for x, y in zip(r["r_peaks_x"], r["r_peaks_y"])]
        if save_previews:
            write_previews(out_dir / Path(name).with_suffix(""), img, r["mask"], r["coords"], r["ecg_y"],
                           r["ecg_present"], r["r_peaks_x"], r["r_peaks_y"])

    if progress:
        progress(len(inputs), len(inputs))
    write_csv(out_dir / "ecg_summary.csv", ["image", "ecg_present", "coverage", "n_r_peaks"], summary)
    write_csv(out_dir / "ecg_trace.csv", ["image", "x", "y"], trace)
    write_csv(out_dir / "r_peaks.csv", ["image", "x", "y"], peaks)
    print(f"\nDone: processed {len(summary)} of {len(inputs)} image(s) -> {out_dir}")
    for name, reason in skipped:
        print(f"  skipped {name}: {reason}")
    return len(summary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", nargs="?", default=ASSETS_DIR,
                        help="screenshot(s), frames + windows.csv, or a filename inside data/ecg/input/ "
                             "(default: all of data/ecg/input/)")
    parser.add_argument("output", nargs="?", default=OUTPUT_DIR,
                        help="output directory (default: data/ecg/output/)")
    parser.add_argument("--no-previews", action="store_true",
                        help="only write the CSVs, not the diagnostic images")
    args = parser.parse_args()
    input_path = Path(args.input)
    if not input_path.exists() and (ASSETS_DIR / input_path).exists():
        input_path = ASSETS_DIR / input_path  # a bare filename
    run(input_path, args.output, save_previews=not args.no_previews)


if __name__ == "__main__":
    main()
