import argparse

import cv2

from config import (
    ASSETS_DIR,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    OUTPUT_DIR,
)
from ocr_engine import determine_mode
from window_extractor import extract_windows


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


def process_frame(filename):
    """Detect active windows, save their crops, and save a labeled preview."""
    image_path = ASSETS_DIR / filename
    frame = cv2.imread(str(image_path))
    if frame is None:
        print(f"[process_frame] ERROR: cv2.imread returned None for {image_path}.")
        raise FileNotFoundError(f"Could not load image: {image_path}")
    print(
        f"[process_frame] Loaded image shape={frame.shape}; height={frame.shape[0]}, width={frame.shape[1]}, channels={frame.shape[2]}, dtype={frame.dtype}."
    )

    # OCR the footer first. The resulting mode decides whether we expect only
    # B-mode or both B-mode and a lower spectral/M-mode window.
    mode = determine_mode(frame)
    windows = extract_windows(frame, mode)
    print(f"[process_frame] Detected mode={mode!r}; windows extracted={list(windows)}." )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[process_frame] Output directory is ready: {OUTPUT_DIR}.")

    # Draw on a copy so the individual crop images and source frame stay clean.
    annotated = frame.copy()
    output_paths = {}
    image_stem = image_path.stem

    # Each entry contains an image crop and its (left, top, right, bottom)
    # coordinates in the original frame.
    for window_name, (window_image, bounds) in windows.items():
        x1, y1, x2, y2 = bounds
        color = BOX_COLORS[window_name]
        label = window_name.replace("_", "-").upper()
        print(
            f"[process_frame] Annotating {label}: bounds "
            f"(left={x1}, top={y1}, right={x2}, bottom={y2}), "
            f"crop shape={window_image.shape}, box color (BGR)={color}."
        )

        # The right and bottom values mark the far edge of the box; thickness
        # controls how many pixels wide the border is.
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 1)

        # Keep the text label inside the image if the box begins near its top.
        cv2.putText(
            annotated,
            label,
            (x1, max(y1 - 10, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            1,
        )

        # Save each active mode crop separately using a descriptive filename.
        crop_path = OUTPUT_DIR / f"{image_stem}_{window_name}.png"
        _save_image(crop_path, window_image)
        output_paths[window_name] = crop_path

    # Save the annotated source frame after all active windows have been drawn.
    annotated_path = OUTPUT_DIR / f"annotated_{image_path.name}"
    _save_image(annotated_path, annotated)
    output_paths["annotated"] = annotated_path
    print(f"[process_frame] Complete. Output files: {output_paths}.")
    return output_paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Detect ultrasound display windows in a frame."
    )
    parser.add_argument(
        "filename",
        nargs="?",
        default="b_spectral_20261005_000356.png",
        help="Image filename inside the assets directory.",
    )
    args = parser.parse_args()
    process_frame(args.filename)
