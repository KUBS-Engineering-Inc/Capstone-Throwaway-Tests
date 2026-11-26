"""Find the Doppler cursor in B-mode views and measure the dark lumen it points at.

Usage:
    python modules/measure_diameter/src/main.py [INPUT] [OUTPUT] [--no-previews]

INPUT is one of (default: all of data/measure_diameter/input/):
  - a B-mode crop, a directory of them, or a bare filename inside
    data/measure_diameter/input/. A JSON file with the same stem next to a crop
    (segment_windows' scale file) supplies cm_per_pixel;
  - full frames plus segment_windows' windows.csv: a directory holding a windows.csv
    and the frames it names, or (as the harness passes it) a directory with two
    folders, one holding windows.csv and the other the frames. Each frame is
    cropped to its B-mode window, and the scale comes from windows.csv.
OUTPUT is a directory (default: data/measure_diameter/output/).

Writes OUTPUT/diameters.csv: one row per lumen candidate (one per threshold
that found one) for each image, with the cursor anchor and the cross-section
width in pixels and, when the scale is known, cm. Coordinates are in B-mode crop
pixels. Images with no usable cursor or lumen are skipped and listed in the log.
Unless --no-previews is given, also writes the cursor preview, green mask and
threshold-sweep preview per image. Widths are threshold-dependent candidates,
not validated diameters.
"""
import argparse
import csv
import json
import math
from pathlib import Path

import cv2
import numpy as np

from config import (
    ASSETS_DIR,
    CURSOR_PREVIEW_SUFFIX,
    GREEN_MASK_SUFFIX,
    LUMEN_SWEEP_PREVIEW_SUFFIX,
    OUTPUT_DIR,
)
from doppler_cursor_extractor import (
    DopplerCursorDetection,
    count_green_pixels,
    create_cursor_preview,
    extract_doppler_cursor,
)
from lumen_extractor import (
    LumenCandidate,
    create_lumen_threshold_sweep_preview,
    extract_lumen_candidates,
)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
CSV_FIELDS = [
    "image", "cursor_x", "cursor_y", "threshold", "width_px", "width_cm",
    "x1", "y1", "x2", "y2", "area_px", "vertical_extent_px", "axis_angle_deg", "wall_contrast",
]


def write_image(image_path: Path, image: np.ndarray) -> None:
    print(f"[Output] Writing image: {image_path}")
    image_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(image_path), image):
        raise OSError(f"Could not write image: {image_path}")
    print(f"[Output] Successfully wrote {image_path.stat().st_size} bytes.")


def save_cursor_debug_outputs(
    out_stem: Path,
    image: np.ndarray,
    detection: DopplerCursorDetection,
) -> None:
    """Save temporary visualizations and print cursor-detection diagnostics.
    Files are named `out_stem` plus a suffix."""
    print("\n=== Saving cursor diagnostics ===")
    preview_path = out_stem.with_name(f"{out_stem.name}{CURSOR_PREVIEW_SUFFIX}")
    mask_path = out_stem.with_name(f"{out_stem.name}{GREEN_MASK_SUFFIX}")

    cursor_preview = create_cursor_preview(
        image,
        detection.green_mask,
        detection.beam,
        detection.insonation_line,
        detection.cursor_center,
    )
    write_image(preview_path, cursor_preview)
    write_image(mask_path, detection.green_mask)

    x1, y1, x2, y2 = detection.beam
    beam_length = math.hypot(x2 - x1, y2 - y1)
    beam_angle_degrees = math.degrees(math.atan2(y2 - y1, x2 - x1))
    print(f"Image size: {image.shape[1]} x {image.shape[0]} pixels")
    print(f"Green pixels detected: {count_green_pixels(detection.green_mask)}")
    print(f"Green line segments detected: {len(detection.line_segments)}")
    print(
        f"Longest segment: ({x1}, {y1}) to ({x2}, {y2}), "
        f"length={beam_length:.1f} px, angle={beam_angle_degrees:.1f} degrees"
    )
    print(f"Cursor overlay saved to: {preview_path}")
    print(f"Green mask saved to: {mask_path}")
    print(f"Fitted insonation line: {detection.insonation_line}")
    print(f"Beam/insonation intersection: {detection.cursor_center}")


def save_lumen_debug_outputs(
    out_stem: Path,
    image: np.ndarray,
    center: tuple[int, int],
    candidates: list[LumenCandidate],
) -> None:
    print("\n=== Saving lumen-candidate diagnostics ===")
    preview_path = out_stem.with_name(f"{out_stem.name}{LUMEN_SWEEP_PREVIEW_SUFFIX}")
    preview = create_lumen_threshold_sweep_preview(image, center, candidates)
    write_image(preview_path, preview)

    print(f"Cursor-anchored point: {center}")
    print(f"Lumen candidates across thresholds: {len(candidates)}")
    for candidate in candidates:
        x, y, width, height = candidate.search_region
        print(
            f"  threshold={candidate.threshold}: "
            f"cross-section width={candidate.cross_section_width_pixels:.1f} px, "
            f"cross-section endpoints={candidate.cross_section}, "
            f"component area={candidate.area_pixels} px, "
            f"vertical extent={candidate.vertical_extent_pixels} px, "
            f"long-axis angle={candidate.axis_angle_degrees:.1f} degrees, "
            f"search region=({x}, {y}, {width}x{height}), "
            f"wall contrast={candidate.wall_contrast:.1f}, "
            f"lumen/ring mean={candidate.lumen_mean_intensity:.1f}/"
            f"{candidate.wall_ring_mean_intensity:.1f}"
        )
    widths = [candidate.cross_section_width_pixels for candidate in candidates]
    print(
        f"Candidate width range across thresholds: "
        f"{min(widths):.1f}..{max(widths):.1f}px; "
        f"mean={float(np.mean(widths)):.1f}px, "
        f"standard deviation={float(np.std(widths)):.1f}px."
    )
    print("These are threshold-dependent candidate extents, not a validated diameter.")
    print(f"Lumen threshold sweep saved to: {preview_path}")


def analyze(image: np.ndarray, out_stem: Path | None = None):
    """Detect the cursor and the lumen candidates at its anchor point.
    Returns (detection, candidates). Raises ValueError if either can't be found.
    With `out_stem`, saves the diagnostic previews named after it."""
    print("\n[Run 1/3] Detecting the green Doppler cursor.")
    detection = extract_doppler_cursor(image)
    if out_stem is not None:
        save_cursor_debug_outputs(out_stem, image, detection)
    if detection.cursor_center is None:
        raise ValueError("Could not fit the insonation stroke and intersect it with the Doppler beam.")

    print(
        "\n[Run 2/3] Using the fitted beam/insonation-line intersection as the "
        "lumen-search anchor; the cursor angle is not used as the vessel angle."
    )
    candidates = extract_lumen_candidates(image, detection.green_mask, detection.cursor_center)
    if not candidates:
        raise ValueError("No dark lumen candidate containing the cursor point was found.")
    print("\n[Run 3/3] Summarizing candidates.")
    if out_stem is not None:
        save_lumen_debug_outputs(out_stem, image, detection.cursor_center, candidates)
    return detection, candidates


def list_images(path):
    path = Path(path)
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGE_EXTS)
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


def _sidecar_scale(img_path: Path):
    """cm_per_pixel from a JSON file with the image's stem, if there is one."""
    json_path = img_path.with_suffix(".json")
    if not json_path.is_file():
        return None
    return json.loads(json_path.read_text()).get("cm_per_pixel")


def load_inputs(path, window="b_mode"):
    """[(name, read, cm_per_pixel or None)] for every input image, where read()
    loads the image (None if unreadable). With segment_windows output, every
    frame is cropped to its `window`; name is the frame's relative path."""
    windows = find_windows(path)
    if windows is None:
        return [(p.name, lambda p=p: cv2.imread(str(p)), _sidecar_scale(p)) for p in list_images(path)]
    csv_path, frames_dir = windows
    with open(csv_path, newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["window"] == window]
    print(f"Reading {len(rows)} {window} window(s) from {csv_path}, frames in {frames_dir}")
    return [(r["image"], _crop_loader(frames_dir / r["image"], r),
             float(r["cm_per_pixel"]) if r.get("cm_per_pixel") else None) for r in rows]

def _crop_loader(frame_path, row):
    """A function that reads the frame and crops it to the window in `row`."""
    def read():
        frame = cv2.imread(str(frame_path))
        if frame is None:
            return None
        left, top, right, bottom = (int(row[k]) for k in ("left", "top", "right", "bottom"))
        return frame[top:bottom, left:right]
    return read



def candidate_rows(name, center, candidates, cm_per_pixel):
    rows = []
    for c in candidates:
        (x1, y1), (x2, y2) = c.cross_section
        rows.append(dict(
            image=name, cursor_x=center[0], cursor_y=center[1], threshold=c.threshold,
            width_px=round(c.cross_section_width_pixels, 2),
            width_cm=round(c.cross_section_width_pixels * cm_per_pixel, 4) if cm_per_pixel else "",
            x1=x1, y1=y1, x2=x2, y2=y2, area_px=c.area_pixels,
            vertical_extent_px=c.vertical_extent_pixels,
            axis_angle_deg=round(c.axis_angle_degrees, 2), wall_contrast=round(c.wall_contrast, 2),
        ))
    return rows


def run(input, output, save_previews=True, progress=None):
    """Measure lumen candidates in every image under `input` (see the module
    docstring for the accepted layouts); write diameters.csv (and, with
    `save_previews`, diagnostic images) to `output`.
    `progress(done, total)`, if given, is called after each image.
    Returns the number of images measured."""
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, skipped = [], []
    inputs = load_inputs(input)
    n_inputs = len(inputs)
    for i, (name, read, cm_per_pixel) in enumerate(inputs):
        if progress:
            progress(i, n_inputs)
        print(f"\n=== B-mode cursor-anchored lumen analysis: {name} ===")
        image = read()
        if image is None:
            skipped.append((name, "unreadable image"))
            continue
        print(f"Image size: {image.shape[1]} x {image.shape[0]} pixels; cm/pixel: {cm_per_pixel}")
        out_stem = out_dir / Path(name).with_suffix("") if save_previews else None
        try:
            detection, candidates = analyze(image, out_stem)
        except ValueError as e:
            print(f"Skipping {name}: {e}")
            skipped.append((name, str(e)))
            continue
        rows += candidate_rows(name, detection.cursor_center, candidates, cm_per_pixel)

    if progress:
        progress(n_inputs, n_inputs)
    with open(out_dir / "diameters.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    measured = n_inputs - len(skipped)
    print(f"\nDone: measured {measured} of {n_inputs} image(s) -> {out_dir / 'diameters.csv'}")
    for name, reason in skipped:
        print(f"  skipped {name}: {reason}")
    return measured


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", nargs="?", default=ASSETS_DIR,
                        help="B-mode crop(s), frames + windows.csv, or a filename inside data/measure_diameter/input/ "
                             "(default: all of data/measure_diameter/input/)")
    parser.add_argument("output", nargs="?", default=OUTPUT_DIR,
                        help="output directory (default: data/measure_diameter/output/)")
    parser.add_argument("--no-previews", action="store_true",
                        help="only write diameters.csv, not the diagnostic images")
    args = parser.parse_args()
    input_path = Path(args.input)
    if not input_path.exists() and (ASSETS_DIR / input_path).exists():
        input_path = ASSETS_DIR / input_path  # a bare filename, as the .bat file passes
    run(input_path, args.output, save_previews=not args.no_previews)


if __name__ == "__main__":
    main()
