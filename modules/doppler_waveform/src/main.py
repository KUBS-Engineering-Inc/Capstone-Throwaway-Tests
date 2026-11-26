"""Extract the white spectral Doppler waveform and its envelope from spectral Doppler screens.

Usage:
    python modules/doppler_waveform/src/main.py [INPUT] [OUTPUT] [--no-previews]

INPUT is one of (default: all of data/doppler_waveform/input/):
  - a full screenshot, a directory of them (searched recursively), or a bare
    filename inside data/doppler_waveform/input/;
  - full frames plus segment_windows' windows.csv: a directory holding a
    windows.csv and the frames it names, or (as the harness passes it) a
    directory with two folders, one holding windows.csv and the other the
    frames. Only frames with a spectral window are processed.
OUTPUT is a directory (default: data/doppler_waveform/output/).

Writes to OUTPUT, keyed by image:
  envelope.csv          image, x, y, detected, interpolated: one row per column
                        of the waveform region. y is the brightness-weighted mean
                        row of the waveform in that column; it is blank where no
                        waveform was found and the gap was too long to fill.
  waveform_summary.csv  image, columns, detected_columns, interpolated_columns,
                        missing_columns, waveform_pixels
Coordinates are full-frame pixels (origin top left); no velocity conversion yet.
Images with no waveform are skipped and listed in the log. Unless --no-previews
is given, also writes the waveform mask and the envelope overlay per image.
The waveform region is a fixed rectangle on the 1024x768 Terason layout.
"""
import argparse
import csv
from pathlib import Path

import cv2
import numpy as np

from config import ASSETS_DIR, OUTPUT_DIR
from previews import write_previews
from waveform_extractor import crop, extract_envelope, extract_waveform

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
WINDOW = "spectral"
SUMMARY_FIELDS = ["image", "columns", "detected_columns", "interpolated_columns",
                  "missing_columns", "waveform_pixels"]


def analyze(img):
    """Return the waveform mask, pixels and envelope of one full screenshot.
    Raises ValueError if no waveform is found."""
    mask, gray, waveform_coords = extract_waveform(img)
    _, offset = crop(img, "waveform")
    envelope_coords, valid = extract_envelope(mask, gray, offset)
    envelope_y = envelope_coords[:, 1]
    return dict(
        mask=mask, waveform_coords=waveform_coords, envelope_coords=envelope_coords,
        valid_columns=valid, interpolated_columns=np.isfinite(envelope_y) & ~valid,
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


def write_csv(path, fields, rows):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(input, output, save_previews=True, progress=None):
    """Extract the waveform envelope from every image under `input` (see the
    module docstring for the accepted layouts) and write the CSVs (and, with
    `save_previews`, diagnostic images) to `output`.
    `progress(done, total)`, if given, is called after each image.
    Returns the number of images processed."""
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)
    inputs = load_inputs(input)
    summary, envelope, skipped = [], [], []
    for i, (name, img_path) in enumerate(inputs):
        if progress:
            progress(i, len(inputs))
        print(f"\n=== Doppler waveform: {name} ===")
        img = cv2.imread(str(img_path))
        if img is None:
            skipped.append((name, "unreadable image"))
            continue
        try:
            r = analyze(img)
        except ValueError as e:
            print(f"Skipping {name}: {e}")
            skipped.append((name, str(e)))
            continue
        xs, ys = r["envelope_coords"][:, 0], r["envelope_coords"][:, 1]
        valid, interpolated = r["valid_columns"], r["interpolated_columns"]
        row = dict(image=name, columns=len(ys), detected_columns=int(valid.sum()),
                   interpolated_columns=int(interpolated.sum()),
                   missing_columns=int(np.isnan(ys).sum()), waveform_pixels=len(r["waveform_coords"]))
        print(", ".join(f"{k}={v}" for k, v in row.items() if k != "image"))
        summary.append(row)
        envelope += [dict(image=name, x=int(x), y="" if np.isnan(y) else round(float(y), 3),
                          detected=bool(d), interpolated=bool(f))
                     for x, y, d, f in zip(xs, ys, valid, interpolated)]
        if save_previews:
            write_previews(out_dir / Path(name).with_suffix(""), img, r["mask"], r["envelope_coords"])

    if progress:
        progress(len(inputs), len(inputs))
    write_csv(out_dir / "waveform_summary.csv", SUMMARY_FIELDS, summary)
    write_csv(out_dir / "envelope.csv", ["image", "x", "y", "detected", "interpolated"], envelope)
    print(f"\nDone: processed {len(summary)} of {len(inputs)} image(s) -> {out_dir}")
    for name, reason in skipped:
        print(f"  skipped {name}: {reason}")
    return len(summary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", nargs="?", default=ASSETS_DIR,
                        help="screenshot(s), frames + windows.csv, or a filename inside "
                             "data/doppler_waveform/input/ (default: all of data/doppler_waveform/input/)")
    parser.add_argument("output", nargs="?", default=OUTPUT_DIR,
                        help="output directory (default: data/doppler_waveform/output/)")
    parser.add_argument("--no-previews", action="store_true",
                        help="only write the CSVs, not the diagnostic images")
    args = parser.parse_args()
    input_path = Path(args.input)
    if not input_path.exists() and (ASSETS_DIR / input_path).exists():
        input_path = ASSETS_DIR / input_path  # a bare filename
    run(input_path, args.output, save_previews=not args.no_previews)


if __name__ == "__main__":
    main()
