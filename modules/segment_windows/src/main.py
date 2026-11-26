"""Find the display windows (B-mode, spectral / M-mode) in full ultrasound screens.

Usage:
    python modules/segment_windows/src/main.py [INPUT] [OUTPUT] [--no-images]

INPUT is an image, a directory of images (searched recursively, e.g. the
per-video folders extract_frames writes), or a bare filename inside
data/segment_windows/input/ (default: all of data/segment_windows/input/).
OUTPUT is a directory (default: data/segment_windows/output/).

Writes OUTPUT/windows.csv: one row per window found, with its full-frame
coordinates. Later stages read the frames plus this file and crop the window
they need, so the crops don't have to be stored:

    image                          mode      window  left top right bottom  top_depth_cm bottom_depth_cm cm_per_pixel
    recording_oct_5/frame_001800.jpg  spectral  b_mode   ...                  0.0          4.0             0.0139
    recording_oct_5/frame_001800.jpg  spectral  spectral ...

`image` is the frame's path relative to INPUT. Coordinates are pixels,
(left, top) inclusive and (right, bottom) exclusive, so the crop is
frame[top:bottom, left:right]. The depth/scale columns are only filled for b_mode.
Frames whose mode or depth can't be read are skipped and listed in the log.

Unless --no-images is given (or run(..., save_images=False)), it also writes, per
frame, the window crops ({stem}_{window}.png), the B-mode scale
({stem}_b_mode_scale.json) and an annotated copy (annotated_{name}) for inspection.
"""
import argparse
import csv
import json
from pathlib import Path

import cv2

from config import (
    ASSETS_DIR,
    B_MODE_FULL_BOTTOM_TICK,
    B_MODE_SPLIT_BOTTOM_TICK,
    B_MODE_TOP_DEPTH_CM,
    B_MODE_TOP_TICK,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    OUTPUT_DIR,
)
from ocr_engine import determine_b_mode_depth_cm, determine_mode
from window_extractor import extract_windows


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
CSV_FIELDS = ["image", "mode", "window", "left", "top", "right", "bottom",
              "top_depth_cm", "bottom_depth_cm", "cm_per_pixel"]

BOX_COLORS = {
    "b_mode": (0, 0, 255),
    "spectral": (0, 255, 0),
    "m_mode": (255, 0, 0),
}


def _save_image(path, image):
    """Write an image and fail loudly if OpenCV reports a save error."""
    print(f"[save_image] Writing image shape={image.shape} to {path}.")
    if not cv2.imwrite(str(path), image):
        raise OSError(f"Could not save image to {path}")
    print(f"[save_image] Successfully saved: {path}")


def _b_mode_scale_metadata(mode, bottom_depth_cm):
    """Build compact depth scale metadata for the B-mode window."""
    bottom_tick_y = (
        B_MODE_FULL_BOTTOM_TICK
        if mode == "b_only"
        else B_MODE_SPLIT_BOTTOM_TICK
    )
    pixel_distance = bottom_tick_y - B_MODE_TOP_TICK
    depth_distance_cm = bottom_depth_cm - B_MODE_TOP_DEPTH_CM
    cm_per_pixel = depth_distance_cm / pixel_distance

    return {
        "cm_per_pixel": cm_per_pixel,
        "horizontal_pixel_spacing_equals_vertical": True,
        "top_depth_cm": B_MODE_TOP_DEPTH_CM,
        "bottom_depth_cm": bottom_depth_cm,
    }


def segment_frame(frame):
    """Return (mode, B-mode scale dict, {window name: (crop, (left, top, right, bottom))}).
    Raises RuntimeError if the frame has the wrong size or OCR can't read it."""
    height, width = frame.shape[:2]
    if (width, height) != (FRAME_WIDTH, FRAME_HEIGHT):
        raise RuntimeError(f"Expected a {FRAME_WIDTH}x{FRAME_HEIGHT} frame, got {width}x{height}.")

    # OCR the footer first. The resulting mode decides whether we expect only
    # B-mode or both B-mode and a lower spectral/M-mode window.
    mode = determine_mode(frame)
    b_mode_depth_cm = determine_b_mode_depth_cm(frame)
    windows = extract_windows(frame, mode)
    print(
        f"[segment_frame] Detected mode={mode!r}; B-mode depth={b_mode_depth_cm:g} cm; "
        f"windows extracted={list(windows)}."
    )
    return mode, _b_mode_scale_metadata(mode, b_mode_depth_cm), windows


def _save_frame_images(out_dir, image_path, frame, windows, scale):
    """Save each window crop, the B-mode scale JSON, and an annotated frame."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # Draw on a copy so the individual crop images and source frame stay clean.
    annotated = frame.copy()
    stem = image_path.stem

    # Each entry contains an image crop and its (left, top, right, bottom)
    # coordinates in the original frame.
    for window_name, (window_image, (x1, y1, x2, y2)) in windows.items():
        color = BOX_COLORS[window_name]
        label = window_name.replace("_", "-").upper()
        # The right and bottom values mark the far edge of the box; thickness
        # controls how many pixels wide the border is.
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 1)
        # Keep the text label inside the image if the box begins near its top.
        cv2.putText(annotated, label, (x1, max(y1 - 10, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1)
        _save_image(out_dir / f"{stem}_{window_name}.png", window_image)

    # Save the crop's scale as data alongside the image so measurement code
    # run on the crops can convert pixel positions/distances to cm.
    scale_path = out_dir / f"{stem}_b_mode_scale.json"
    with scale_path.open("w", encoding="utf-8") as scale_file:
        json.dump({"b_mode_crop": f"{stem}_b_mode.png", **scale}, scale_file, indent=2)
        scale_file.write("\n")
    _save_image(out_dir / f"annotated_{image_path.name}", annotated)


def list_images(path):
    """[(image path, key)] where key is the path relative to `path` (or the file name)."""
    path = Path(path)
    if path.is_file():
        return [(path, path.name)]
    if path.is_dir():
        return [(p, p.relative_to(path).as_posix()) for p in sorted(path.rglob("*"))
                if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    raise FileNotFoundError(f"Input not found: {path}")


def run(input, output, save_images=True, progress=None):
    """Find the windows in every image under `input`; write windows.csv (and, with
    `save_images`, crops and annotated frames) to `output`.
    `progress(done, total)`, if given, is called after each image.
    Returns the number of frames segmented."""
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)
    images = list_images(input)

    rows, skipped = [], []
    for i, (image_path, key) in enumerate(images):
        if progress:
            progress(i, len(images))
        print(f"\n=== {key} ===")
        frame = cv2.imread(str(image_path))
        if frame is None:
            skipped.append((key, "unreadable image"))
            continue
        try:
            mode, scale, windows = segment_frame(frame)
        except RuntimeError as e:
            print(f"[run] Skipping {key}: {e}")
            skipped.append((key, str(e)))
            continue

        for window_name, (_, (x1, y1, x2, y2)) in windows.items():
            row = dict(image=key, mode=mode, window=window_name, left=x1, top=y1, right=x2, bottom=y2)
            if window_name == "b_mode":
                row.update(top_depth_cm=scale["top_depth_cm"], bottom_depth_cm=scale["bottom_depth_cm"],
                           cm_per_pixel=round(scale["cm_per_pixel"], 8))
            rows.append(row)
        if save_images:
            _save_frame_images(out_dir / Path(key).parent, image_path, frame, windows, scale)

    if progress:
        progress(len(images), len(images))
    with open(out_dir / "windows.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    segmented = len(images) - len(skipped)
    print(f"\nDone: segmented {segmented} of {len(images)} image(s) -> {out_dir / 'windows.csv'}")
    for key, reason in skipped:
        print(f"  skipped {key}: {reason}")
    return segmented


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", nargs="?", default=ASSETS_DIR,
                        help="image, directory of images, or a filename inside data/segment_windows/input/ "
                             "(default: all of data/segment_windows/input/)")
    parser.add_argument("output", nargs="?", default=OUTPUT_DIR,
                        help="output directory (default: data/segment_windows/output/)")
    parser.add_argument("--no-images", action="store_true",
                        help="only write windows.csv, not the crops and annotated frames")
    args = parser.parse_args()
    input_path = Path(args.input)
    if not input_path.exists() and (ASSETS_DIR / input_path).exists():
        input_path = ASSETS_DIR / input_path  # a bare filename, as the .bat file passes
    run(input_path, args.output, save_images=not args.no_images)


if __name__ == "__main__":
    main()
