"""Draw configured ROIs, search limits, and detected windows for inspection."""

import argparse

import cv2

from config import (
    ASSETS_DIR,
    FOOTER_ROI,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    OUTPUT_DIR,
    SPECTRAL_WINDOW,
)
from ocr_engine import determine_mode
from window_extractor import extract_windows, get_b_mode_search_bounds


# OpenCV colors are BGR. One-pixel outlines keep the underlying frame visible.
COLORS = {
    "footer ROI": (255, 0, 0),
    "spectral plot ROI": (0, 255, 255),
    "B-mode search area": (255, 255, 0),
    "detected B-mode": (0, 0, 255),
    "detected lower mode": (0, 255, 0),
}


def draw_bounds(image, bounds, color, label):
    """Draw one pixel of outline around (left, top, right, bottom) bounds."""
    left, top, right, bottom = bounds

    # Config bounds use an exclusive right/bottom edge for image slicing.
    # cv2.rectangle includes its ending point, so subtract one to align them.
    cv2.rectangle(image, (left, top), (right - 1, bottom - 1), color, 1)

    # Keep the image itself unobstructed; the label and color are reported in
    # the terminal instead of being printed over the screenshot.
    print(
        f"[preview_bounds] Drew {label}: "
        f"left={left}, top={top}, right={right}, bottom={bottom}, "
        f"width={right - left}, height={bottom - top}, BGR={color}."
    )


def preview_bounds(filename):
    """Save a source-frame preview with configured and detected bounds."""
    image_path = ASSETS_DIR / filename
    print(f"[preview_bounds] Loading source image: {image_path}")
    frame = cv2.imread(str(image_path))
    if frame is None:
        raise FileNotFoundError(f"Could not load image: {image_path}")

    height, width = frame.shape[:2]
    print(f"[preview_bounds] Source frame dimensions: width={width}, height={height}.")
    if (width, height) != (FRAME_WIDTH, FRAME_HEIGHT):
        raise ValueError(
            f"Expected a {FRAME_WIDTH}x{FRAME_HEIGHT} frame, "
            f"got {width}x{height}: {image_path}"
        )

    # Use the same OCR and extraction functions as the main program so the
    # preview shows the bounds that would actually be used for this frame.
    mode = determine_mode(frame)
    windows = extract_windows(frame, mode)
    print(f"[preview_bounds] Detected mode={mode!r}; detected windows={list(windows)}.")
    print("[preview_bounds] Color key (BGR):")
    for label, color in COLORS.items():
        print(f"  {label}: {color}")

    preview = frame.copy()

    # Always draw the fixed ROIs, including the spectral ROI on B-only frames,
    # so it is easy to compare their configured positions across screenshots.
    draw_bounds(preview, FOOTER_ROI, COLORS["footer ROI"], "footer ROI")
    draw_bounds(
        preview,
        SPECTRAL_WINDOW,
        COLORS["spectral plot ROI"],
        "spectral plot ROI",
    )

    # This outline shows the full region examined by the B-mode contour finder.
    search_bounds = get_b_mode_search_bounds(mode)
    draw_bounds(
        preview,
        search_bounds,
        COLORS["B-mode search area"],
        "B-mode search area",
    )

    # Draw the resulting crops as well, so the search region can be compared
    # with the actual detector output.
    for window_name, (_, bounds) in windows.items():
        color_name = "detected B-mode" if window_name == "b_mode" else "detected lower mode"
        draw_bounds(preview, bounds, COLORS[color_name], color_name)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"bounds_preview_{image_path.name}"
    if not cv2.imwrite(str(output_path), preview):
        raise OSError(f"Could not save bounds preview to {output_path}")
    print(f"[preview_bounds] Saved preview image: {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Overlay configured search areas and detected windows on a frame."
    )
    parser.add_argument(
        "filename",
        nargs="?",
        default="b_spectral_20261005_000356.png",
        help="Image filename inside data/segment_windows/input/.",
    )
    preview_bounds(parser.parse_args().filename)
