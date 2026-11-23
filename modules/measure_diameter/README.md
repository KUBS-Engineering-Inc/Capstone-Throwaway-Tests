# Measuring Perpendicular Diameter - Feasibility Testing

Finds the green Doppler cursor in an ultrasound screenshot, then searches for the dark vessel lumen where the cursor's lines cross and reports candidate cross-section widths in pixels.

## How to Run
Ensure you have Python installed and have the libraries listed in `requirements.txt` set up. 

The script we are targetting is `main.py` in `src`, which will take data from `data/measure_diameter/input` as input and output into `data/measure_diameter/output`. 

### Method 1 (If you've created a virtual environment)
From your file explorer, double-click on `measure_diameter.bat` in this folder to run the script. This script will activate a virtual environment to access the necessary libraries. On the fourth line, it executes the main script via:
```bash
python src\main.py 
```
The script processes every image in `data/measure_diameter/input`. To process one image, append its file name to the end of that line, as shown below:
```bash
python src\main.py 0529_b_spectral_3cm.png
```

### Method 2 (No virtual environment)
If you have the libaries installed in another manner, you can open a terminal, and from the root directory run:
```bash
python modules/measure_diameter/src/main.py
```
Again, if you need a specific file, append its file name (or any image path or folder) to the end of the line. A second argument sets the output folder, and `--no-previews` writes only `diameters.csv`.

From Python, or from the harness, call `run(input, output, save_previews=True)`. The harness's vessels pipeline runs it on the extracted video frames, cropped to the B-mode window with `segment_windows`' `windows.csv`, with `save_previews=False`.

## What it Does
**Input**: One of:
- B-mode crops: an image, a folder of images, or a filename inside `data/measure_diameter/input` (with no argument, every image there). A JSON file with the same name next to a crop (`segment_windows`' scale file) supplies the centimeters per pixel.
- Full frames plus `segment_windows`' `windows.csv`: a folder holding `windows.csv` next to the frames, or a folder with two subfolders, one holding `windows.csv` and the other the frames (the layout the harness passes). Each frame is cropped to its B-mode window, and the scale comes from `windows.csv`.

**Output**: Writes to `data/measure_diameter/output`:

`diameters.csv`: one row per lumen candidate (one per threshold that found one) for each image: `image`, the cursor anchor (`cursor_x`, `cursor_y`), `threshold`, the cross-section width (`width_px`, and `width_cm` when the scale is known), its endpoints (`x1`, `y1`, `x2`, `y2`), `area_px`, `vertical_extent_px`, `axis_angle_deg` and `wall_contrast`. Coordinates are in B-mode crop pixels. Images with no usable cursor or lumen (e.g. B-only frames) are skipped and listed at the end of the log instead of stopping the run.

Unless `--no-previews` is given, it also writes these diagnostic images, named from the input image:
1. `{input_image_name}_cursor_preview.png`: The detected "Doppler cursor" (Doppler beam,  insonation line, and bound gates) overlaid on the image.
2. `{input_image_name}_green_mask.png`: A mask of the detected green cursor pixels.
3. `{input_image_name}_lumen_threshold_sweep.png`: A grid showing accepted lumen candidates and their cross-sections at different pixel-intensity thresholds. This image is written only if candidates are found. *The reported widths are in pixels and are not validated physical diameters.*

### Execution
1. **Load the Images.** Load each input image (cropping frames to their B-mode window when given `windows.csv`), with its centimeters per pixel if known.
2. **Detect the Cursor.** Detect green pixels and use them to identify the Doppler beam and fit the insonation line. Their intersection becomes the anchor point for the lumen search. Save the cursor preview and green mask, and print detection diagnostics.
3. **Search for Lumen Candidates.** Search a region around the anchor for dark lumen candidates. Sweep through several intensity thresholds, keeping components that contain the anchor and pass basic size checks.
4. **Report Results.** If no anchor or lumen candidates are found, skip the image. Otherwise, add each candidate to `diameters.csv`, create the threshold-sweep preview and print each candidate's cross-section width and other diagnostic measurements.


### Assumptions & Limits
This feasibility test assumes that:
- The Doppler cursor is visible and green enough for the configured color detection to find it.
- The vessel lumen is visible, and the intersection falls within a dark region that can be identified as a lumen candidate.

The threshold and component-size checks are heuristic, so image quality and contrast can affect whether candidates are found and what widths are reported. Widths are measured in pixels, and converted to cm with `segment_windows`' OCR-based scale when it is available; that scale is not yet validated, so these are not physical diameters. This prototype does not produce a validated measurement.

## Design Decision
**Use the Doppler cursor as a search anchor.** When users are using Doppler ultrasound to extract blood-flow information, a Doppler cursor is often present. Using its intersection with the insonation line narrows the area the program needs to search for the lumen. We initially explored detecting the vessel walls directly, but ultrasound image variation and irregular vessel boundaries make it difficult to find continuous walls reliably. The lumen may be a more robust target because it occupies a larger region than the vessel wall's narrow cross-section.

**Calculate the cursor intersection from fitted lines.** Initially, we masked the vertical Doppler beam and estimated its intersection with the insonation line from the midpoint between the two remaining stroke segments. For a small cursor, however, masking the beam can also erase a substantial part of the insonation line, making that midpoint inaccurate. The current approach detects the beam and the remaining insonation-stroke pixels from the green mask, fits the insonation line, and calculates where it crosses the beam.

**Determine an appropriate lumen threshold.** The current threshold sweep helps us inspect how candidate regions change with intensity, but more representative data is needed to choose an optimal threshold. We also need to define the error metric to minimize when evaluating how well a threshold captures the vessel lumen.

### Future Considerations
- Gather more ultrasound data to test with and determine optimal pixel intensity thresholds for lumen classification (define optimality in this scenario - research metrics for accuracy/error in ultrasound measrurements).
- Further explore lumen detection vs blood vessel wall detection - simulate for speed, accuracy, robustness.


