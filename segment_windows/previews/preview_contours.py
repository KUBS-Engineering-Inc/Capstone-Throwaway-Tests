"""Save a binary-mask image and a frame overlay to inspect B-mode contours."""

import argparse

import cv2

from config import ASSETS_DIR, FRAME_HEIGHT, FRAME_WIDTH, OUTPUT_DIR
from ocr_engine import determine_mode
from window_extractor import find_b_mode_contours


def preview_contours(filename):
    """Visualize every detected contour and highlight the largest candidate."""
    image_path = ASSETS_DIR / filename
    print(f"[preview_contours] Loading source frame: {image_path}")
    frame = cv2.imread(str(image_path))
    if frame is None:
        raise FileNotFoundError(f"Could not load image: {image_path}")

    height, width = frame.shape[:2]
    if (width, height) != (FRAME_WIDTH, FRAME_HEIGHT):
        raise ValueError(
            f"Expected a {FRAME_WIDTH}x{FRAME_HEIGHT} frame, "
            f"got {width}x{height}: {image_path}"
        )

    mode = determine_mode(frame)
    search_bounds, thresholded, contours = find_b_mode_contours(frame, mode)
    left, top, right, bottom = search_bounds
    print(
        f"[preview_contours] Mode={mode!r}; search bounds="
        f"(left={left}, top={top}, right={right}, bottom={bottom}); "
        f"contour count={len(contours)}."
    )

    # Save the exact black-and-white search image passed to findContours.
    threshold_path = OUTPUT_DIR / f"contours_threshold_{image_path.stem}.png"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(threshold_path), thresholded):
        raise OSError(f"Could not save threshold image to {threshold_path}")
    print(f"[preview_contours] Saved threshold mask: {threshold_path}")

    # Draw every contour on a copy of the original frame. Contour coordinates
    # are local to the search crop, so offset them to full-frame coordinates.
    overlay = frame.copy()
    cv2.rectangle(overlay, (left, top), (right - 1, bottom - 1), (255, 255, 0), 1)
    cv2.drawContours(
        overlay,
        contours,
        -1,
        (255, 0, 255),
        1,
        offset=(left, top),
    )

    if contours:
        ranked = sorted(contours, key=cv2.contourArea, reverse=True)
        for rank, contour in enumerate(ranked[:10], start=1):
            area = cv2.contourArea(contour)
            x, y, box_width, box_height = cv2.boundingRect(contour)
            bounds = (
                x + left,
                y + top,
                x + left + box_width,
                y + top + box_height,
            )
            print(
                f"[preview_contours] Candidate {rank}: area={area:.1f}; "
                f"full-frame bounds={bounds}."
            )

        # Emphasize the largest contour and its upright bounding rectangle.
        largest = ranked[0]
        x, y, box_width, box_height = cv2.boundingRect(largest)
        box_left, box_top = x + left, y + top
        box_right, box_bottom = box_left + box_width, box_top + box_height
        cv2.drawContours(
            overlay,
            [largest],
            -1,
            (0, 0, 255),
            2,
            offset=(left, top),
        )
        cv2.rectangle(
            overlay,
            (box_left, box_top),
            (box_right - 1, box_bottom - 1),
            (0, 255, 0),
            1,
        )
        print(
            f"[preview_contours] Largest contour is red; its bounding box is "
            f"green: (left={box_left}, top={box_top}, "
            f"right={box_right}, bottom={box_bottom})."
        )
    else:
        print("[preview_contours] No contours to draw.")

    overlay_path = OUTPUT_DIR / f"contours_overlay_{image_path.name}"
    if not cv2.imwrite(str(overlay_path), overlay):
        raise OSError(f"Could not save contour overlay to {overlay_path}")
    print(f"[preview_contours] Saved contour overlay: {overlay_path}")
    return threshold_path, overlay_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Visualize the threshold mask and B-mode contours for an image."
    )
    parser.add_argument(
        "filename",
        nargs="?",
        default="b_spectral_20261005_000356.png",
        help="Image filename inside the assets directory.",
    )
    preview_contours(parser.parse_args().filename)
