# main.py
import argparse

import cv2
from pathlib import Path
from config import ASSETS_DIR
from ocr_engine import determine_mode, ocr_words, fit_axis
from window_extractor import extract_windows
from image_utils import crop, prep_cyan, prep_light_on_dark

def process_frame(filename):
    # Dynamically build paths
    image_path = ASSETS_DIR / filename
    output_path = ASSETS_DIR / f"annotated_{filename}"
    
    # Load the frame
    frame = cv2.imread(str(image_path))
    if frame is None:
        print(f"Error: Could not load image at {image_path}")
        return

    # 1. Detect Layout Mode
    mode = determine_mode(frame)
    print(f"Mode: {mode}")
    
    # 2. Extract Bounding Boxes & Image Crops
    windows = extract_windows(frame, mode)
    
    # Create a copy of the frame specifically for drawing our boxes
    annotated_frame = frame.copy()
    
    # 3. Draw Bounding Boxes
    # Draw B-Mode (Red Box)
    if 'b_mode_coords' in windows:
        bc = windows['b_mode_coords']
        cv2.rectangle(annotated_frame, (bc['x1'], bc['y1']), (bc['x2'], bc['y2']), (0, 0, 255), 2)
        cv2.putText(annotated_frame, "B-MODE", (bc['x1'], bc['y1'] - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        print(f"B-Mode Extracted at: {bc}")
        
    # Draw Spectral / M-Mode (Green Box)
    if f"{mode}_coords" in windows:
        bc = windows[f"{mode}_coords"]
        cv2.rectangle(annotated_frame, (bc['x1'], bc['y1']), (bc['x2'], bc['y2']), (0, 255, 0), 2)
        cv2.putText(annotated_frame, mode.upper(), (bc['x1'], bc['y1'] - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    # Save the annotated image to visually verify it worked
    cv2.imwrite(str(output_path), annotated_frame)
    print(f"Saved annotated preview to: {output_path}")
    
    # 4. Calibrate Axes
    if mode in ['spectral', 'm_mode']:
        # Calibrate Velocity/Depth Axis
        vel_roi, vel_off = crop(frame, "velocity_axis")
        vel_words = ocr_words(prep_light_on_dark(vel_roi), vel_off, psm=11, whitelist="-0123456789")
        vel_calibration = fit_axis(vel_words)
        if vel_calibration:
            a, b = vel_calibration
            print(f"Bottom Axis Calibration: value = {a:.4f} * pixel_y + {b:.2f}")

    # Calibrate B-Mode Depth Scale
    scale_name = "depth_scale_b_only" if mode == 'b_only' else "depth_scale"
    depth_roi, depth_off = crop(frame, scale_name)
    depth_words = ocr_words(prep_cyan(depth_roi), depth_off, psm=11, whitelist="0123456789")
    depth_calibration = fit_axis(depth_words)
    if depth_calibration:
        a, b = depth_calibration
        print(f"B-Mode Depth Calibration: cm = {a:.4f} * pixel_y + {b:.2f}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process and extract data from an ultrasound frame.")
    parser.add_argument(
        "filename", 
        type=str, 
        nargs='?', 
        default="b_spectral_20261005_000356.png", 
        help="The filename of the image inside the assets directory (optional)"
    )
    
    args = parser.parse_args()
    process_frame(args.filename)