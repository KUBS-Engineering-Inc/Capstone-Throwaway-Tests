# Segmenting Windows in an Ultrasound Video Frame - Feasibility Testing

Splits an ultrasound screenshot into its display windows (B-mode, plus the spectral or M-mode window when present) and works out the B-mode's centimeters per pixel from the OCR-read depth.

## How to Run
Ensure you have Python installed and the libraries listed in `requirements.txt` set up.

The script is `main.py` in `src`. It reads images from `data/segment_windows/input` and writes results to `data/segment_windows/output`.

### Method 1 (If you've created a virtual environment)
From your file explorer, double-click on `segment_windows.bat` in this folder to run the script. This script will activate a virtual environment to access the necessary libraries. On the fourth line, it executes the main script via:
```bash
python src\main.py 
```
The script processes every image in `data/segment_windows/input`. To process one image, append its filename to the command, as shown below:
```bash
python src\main.py b_mode_only_20261005_000010.png
```

### Method 2 (No virtual environment)
If you have the libraries installed another way, open a terminal and run this command from the repository root:
```bash
python modules/segment_windows/src/main.py
```
To process a specific file, append its filename (or any image path or folder) to the command. A second argument sets the output folder, and `--no-images` writes only `windows.csv`.

From Python, or from the harness, call `run(input, output, save_images=True)`. The harness's vessels pipeline runs it on the extracted video frames with `save_images=False`, so only the coordinates are written.

## What it Does
**Input**: An image, a folder of images (searched recursively, e.g. the per-video folders `extract_frames` writes), or a filename inside `data/segment_windows/input`. With no argument, every image in `data/segment_windows/input`.

**Output**: Writes to `data/segment_windows/output`:

`windows.csv`: one row per window found in each frame. This is what later stages read: they take the frames plus these coordinates and crop the window they need themselves.

| Column | Meaning |
|---|---|
| `image` | the frame's path relative to the input folder, e.g. `recording_oct_5/frame_001800.jpg` |
| `mode` | `b_only`, `spectral` or `m_mode` |
| `window` | `b_mode`, `spectral` or `m_mode` |
| `left`, `top`, `right`, `bottom` | the window's box in full-frame pixels; the crop is `frame[top:bottom, left:right]` |
| `top_depth_cm`, `bottom_depth_cm`, `cm_per_pixel` | B-mode depth scale (only filled on `b_mode` rows) |

Frames whose depth can't be read, or that aren't 1024 × 768, are skipped and listed at the end of the log instead of stopping the run.

Unless `--no-images` is given, it also writes these files per frame for inspection:
1. `{input_stem}_b_mode.png`: The extracted B-mode window.
2. `{input_stem}_spectral.png` or `{input_stem}_m_mode.png`: The extracted lower window, written only when the corresponding mode is detected.
3. `{input_stem}_b_mode_scale.json`: B-mode depth and pixel-scale metadata, including the calculated centimeters per pixel.
4. `annotated_{input_filename}`: The original frame with labeled boxes around the extracted windows. The B-mode box is red, the spectral box green, and the M-mode box blue.

### Execution
1. **Load the Frames.** Read each selected image, checking it is 1024 × 768.
2. **Read the Display Mode and Depth.** Use OCR on fixed footer and side-panel regions to determine whether the frame is B-only, spectral, or M-mode, and to read the displayed B-mode depth. If the depth cannot be read, skip the frame. If neither spectral nor M-mode is recognized in the footer, use the B-only layout.
3. **Find and Crop the Windows.** Threshold a grayscale search area and use its largest bright contour to determine the B-mode window's horizontal bounds; use the known depth-scale tick locations for its vertical bounds. For spectral and M-mode layouts, also crop the lower window using its configured fixed bounds.
4. **Record the Coordinates and Scale.** Add each window's box to `windows.csv`. For the B-mode window, calculate centimeters per pixel from the OCR-read depth and configured tick positions.
5. **Save Crops and an Annotated Preview** (unless `--no-images`). Save each window crop, the B-mode scale JSON, and a copy of the frame with labeled boxes around the windows.

### Assumptions & Limits
This feasibility test assumes that:
- Input frames match the configured 1024 × 768 display layout and the OCR and window-search regions remain in the configured locations.
- The footer and B-mode depth label are legible to OCR. If the footer mode is not recognized, the script assumes a B-only layout; if the depth label is not recognized, the frame is skipped.

## Design Decision
**Identify the layout, then combine fixed coordinates with contour detection.** We initially considered using temporal variance between frames to find regions of interest, but different display modes can change the windows' sizes and positions. A YOLO model was another option, but it would require manually labeling training data. Instead, the program uses OCR to identify the layout, then combines configured coordinates for stable regions with contour detection for variable B-mode bounds (as the width of the B-mode box can change based on the depth). The current implementation reads the footer to identify the mode; OCR of display-specific scale labels, such as a velocity label for spectral mode or a depth label for M-mode, could also be explored.

**Use the depth-scale ticks to derive B-mode scale.** Instead of separately detecting the scale, the program aligns the B-mode crop's top and bottom edges with the known top and bottom depth ticks. Combined with the OCR-read depth, the pixel distance between those ticks gives a centimeters-per-pixel value for downstream conversion.

**Pass coordinates downstream instead of crops.** For video, saving a crop of every window of every frame would add one or two images per frame. The program instead writes each window's box in full-frame coordinates (with the B-mode scale) to one `windows.csv`, and later stages crop the original frame themselves. The crops and annotated frames are still available for inspection, but are optional. A CSV was chosen over per-frame JSON files because the harness compares CSVs row by row.

### Future Considerations
- Validate the depth-scale calculation and its pixel-spacing assumptions against known measurements.
- OCR runs twice per frame. For long videos, reading the mode and depth once per stretch of frames with the same layout would be faster.