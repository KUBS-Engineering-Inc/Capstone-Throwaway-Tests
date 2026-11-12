import argparse
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


def _b_mode_scale_metadata(filename, mode, bottom_depth_cm):
    """Build compact depth scale metadata for the extracted B-mode crop."""
    bottom_tick_y = (
        B_MODE_FULL_BOTTOM_TICK
        if mode == "b_only"
        else B_MODE_SPLIT_BOTTOM_TICK
    )
    pixel_distance = bottom_tick_y - B_MODE_TOP_TICK
    depth_distance_cm = bottom_depth_cm - B_MODE_TOP_DEPTH_CM
    cm_per_pixel = depth_distance_cm / pixel_distance

    return {
        "b_mode_crop": f"{Path(filename).stem}_b_mode.png",
        "cm_per_pixel": cm_per_pixel,
        "horizontal_pixel_spacing_equals_vertical": True,
        "top_depth_cm": B_MODE_TOP_DEPTH_CM,
        "bottom_depth_cm": bottom_depth_cm,
    }


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
    b_mode_depth_cm = determine_b_mode_depth_cm(frame)
    windows = extract_windows(frame, mode)
    print(
        f"[process_frame] Detected mode={mode!r}; B-mode depth={b_mode_depth_cm:g} cm; "
        f"windows extracted={list(windows)}."
    )

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

        if window_name == "b_mode":
            # Save the crop's scale as data alongside the image so downstream
            # measurement code can convert pixel positions/distances to cm.
            scale_data = _b_mode_scale_metadata(
                image_path.name,
                mode,
                b_mode_depth_cm,
            )
            scale_path = OUTPUT_DIR / f"{image_stem}_b_mode_scale.json"
            print(
                f"[process_frame] B-mode depth scale: "
                f"{scale_data['top_depth_cm']:g}-{scale_data['bottom_depth_cm']:g} cm "
                f"({scale_data['cm_per_pixel']:.6f} cm/pixel)."
            )
            with scale_path.open("w", encoding="utf-8") as scale_file:
                json.dump(scale_data, scale_file, indent=2)
                scale_file.write("\n")
            print(f"[process_frame] Saved B-mode scale metadata: {scale_path}")
            output_paths["b_mode_scale"] = scale_path

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
        help="Image filename inside data/segment_windows/input/.",
    )
    args = parser.parse_args()
    process_frame(args.filename)
