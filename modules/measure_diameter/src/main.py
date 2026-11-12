import argparse
import math
from pathlib import Path

import cv2
import numpy as np

from config import (
    ASSETS_DIR,
    CURSOR_PREVIEW_SUFFIX,
    DEFAULT_INPUT_FILENAME,
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


def write_image(image_path: Path, image: np.ndarray) -> None:
    print(f"[Output] Writing image: {image_path}")
    if not cv2.imwrite(str(image_path), image):
        raise OSError(f"Could not write image: {image_path}")
    print(f"[Output] Successfully wrote {image_path.stat().st_size} bytes.")


def save_cursor_debug_outputs(
    image_path: Path,
    image: np.ndarray,
    detection: DopplerCursorDetection,
) -> None:
    """Save temporary visualizations and print cursor-detection diagnostics."""
    print("\n=== Saving cursor diagnostics ===")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    preview_path = OUTPUT_DIR / f"{image_path.stem}{CURSOR_PREVIEW_SUFFIX}"
    mask_path = OUTPUT_DIR / f"{image_path.stem}{GREEN_MASK_SUFFIX}"

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
    print(f"Input image: {image_path}")
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
    image_path: Path,
    image: np.ndarray,
    center: tuple[int, int],
    candidates: list[LumenCandidate],
) -> None:
    print("\n=== Saving lumen-candidate diagnostics ===")
    preview_path = OUTPUT_DIR / f"{image_path.stem}{LUMEN_SWEEP_PREVIEW_SUFFIX}"
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


def main(filename: str) -> None:
    print("=== B-mode cursor-anchored lumen analysis ===")
    input_filename = Path(filename)
    if input_filename.name != filename:
        raise SystemExit("Provide an image filename, not a path.")

    image_path = ASSETS_DIR / input_filename
    print(f"[Run 1/4] Requested image filename: {input_filename}")
    print(f"[Run 1/4] Resolving input to: {image_path}")
    image = cv2.imread(str(image_path))
    if image is None:
        raise SystemExit(f"Could not read image: {image_path}")
    print(
        f"[Run 1/4] Image loaded: width={image.shape[1]}px, "
        f"height={image.shape[0]}px, channels={image.shape[2]}."
    )

    print("\n[Run 2/4] Detecting the green Doppler cursor.")
    try:
        detection = extract_doppler_cursor(image)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    save_cursor_debug_outputs(image_path, image, detection)
    if detection.cursor_center is None:
        raise SystemExit(
            "Could not fit the insonation stroke and intersect it with the Doppler beam."
        )

    print(
        "\n[Run 3/4] Using the fitted beam/insonation-line intersection as the "
        "lumen-search anchor; the cursor angle is not used as the vessel angle."
    )
    candidates = extract_lumen_candidates(
        image,
        detection.green_mask,
        detection.cursor_center,
    )
    if not candidates:
        raise SystemExit("No dark lumen candidate containing the cursor point was found.")
    print("\n[Run 4/4] Summarizing candidates and saving the threshold-sweep preview.")
    save_lumen_debug_outputs(
        image_path,
        image,
        detection.cursor_center,
        candidates,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Inspect cursor-anchored lumen candidates in a B-mode crop."
    )
    parser.add_argument(
        "filename",
        type=str,
        nargs="?",
        default=DEFAULT_INPUT_FILENAME,
        help="The filename of the image inside data/measure_diameter/input/.",
    )

    args = parser.parse_args()
    main(args.filename)
