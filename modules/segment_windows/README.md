# Segmenting Windows in an Ultrasound Video Frame - Feasibility Testing

## How to Run
Ensure you have Python installed and the libraries listed in `requirements.txt` set up.

The script is `main.py` in `src`. It reads images from `data/segment_windows/input` and writes results to `data/segment_windows/output`.

### Method 1 (If you've created a virtual environment)
From your file explorer, double-click on `segment_windows.bat` in this folder to run the script. This script will activate a virtual environment to access the necessary libraries. On the fourth line, it executes the main script via:
```bash
python src\main.py 
```
The script defaults to `b_spectral_20261005_000356.png`. To choose another input image, append its filename to the command, as shown below:
```bash
python src\main.py b_mode_only_20261005_000010.png
```

### Method 2 (No virtual environment)
If you have the libraries installed another way, open a terminal and run this command from the repository root:
```bash
python modules/segment_windows/src/main.py
```
To process a specific file, append its filename to the command.

## What it Does
**Input**: Reads the optional image filename from `data/segment_windows/input`. If no filename is provided, it uses `b_spectral_20261005_000356.png`.

**Output**: Writes the extracted windows and an annotated copy of the input image to `data/segment_windows/output`:
1. `{input_stem}_b_mode.png`: The extracted B-mode window.
2. `{input_stem}_spectral.png` or `{input_stem}_m_mode.png`: The extracted lower window, written only when the corresponding mode is detected.
3. `{input_stem}_b_mode_scale.json`: B-mode depth and pixel-scale metadata, including the calculated centimeters per pixel.
4. `annotated_{input_filename}`: The original frame with labeled boxes around the extracted windows. The B-mode box is red, the spectral box green, and the M-mode box blue.

### Execution
1. **Load the Frame.** Read the selected image from the input directory.
2. **Read the Display Mode and Depth.** Use OCR on fixed footer and side-panel regions to determine whether the frame is B-only, spectral, or M-mode, and to read the displayed B-mode depth. If the depth cannot be read, stop with an error. If neither spectral nor M-mode is recognized in the footer, use the B-only layout.
3. **Find and Crop the Windows.** Threshold a grayscale search area and use its largest bright contour to determine the B-mode window's horizontal bounds; use the known depth-scale tick locations for its vertical bounds. For spectral and M-mode layouts, also crop the lower window using its configured fixed bounds.
4. **Save the Crops and Scale.** Save each active window crop. For the B-mode crop, calculate centimeters per pixel from the OCR-read depth and configured tick positions, then save that information in the scale JSON file.
5. **Save an Annotated Preview.** Draw labeled boxes around the detected windows on a copy of the original frame and save it alongside the crops.

### Assumptions & Limits
This feasibility test assumes that:
- Input frames match the configured 1024 × 768 display layout and the OCR and window-search regions remain in the configured locations.
- The footer and B-mode depth label are legible to OCR. If the footer mode is not recognized, the script assumes a B-only layout; if the depth label is not recognized, processing stops with an error.

## Design Decision
**Identify the layout, then combine fixed coordinates with contour detection.** We initially considered using temporal variance between frames to find regions of interest, but different display modes can change the windows' sizes and positions. A YOLO model was another option, but it would require manually labeling training data. Instead, the program uses OCR to identify the layout, then combines configured coordinates for stable regions with contour detection for variable B-mode bounds (as the width of the B-mode box can change based on the depth). The current implementation reads the footer to identify the mode; OCR of display-specific scale labels, such as a velocity label for spectral mode or a depth label for M-mode, could also be explored.

**Use the depth-scale ticks to derive B-mode scale.** Instead of separately detecting the scale, the program aligns the B-mode crop's top and bottom edges with the known top and bottom depth ticks. Combined with the OCR-read depth, the pixel distance between those ticks gives a centimeters-per-pixel value for downstream conversion.

**Keep the current crops, but consider passing coordinates downstream.** The program currently saves cropped window images and a JSON file with B-mode depth-scale metadata. For large image sets, a future version could instead save the bounding-box coordinates relative to each full image, allowing downstream processing to use the original image and ROI reference without creating and passing separate crop files.

### Future Considerations
- Validate the depth-scale calculation and its pixel-spacing assumptions against known measurements.
- Evaluate whether coordinate-only JSON output would simplify downstream processing and reduce work when handling large image sets.