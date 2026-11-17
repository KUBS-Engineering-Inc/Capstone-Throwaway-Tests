# Measuring Perpendicular Diameter - Feasibility Testing

## How to Run
Ensure you have Python installed and have the libraries listed in `requirements.txt` set up. 

The script we are targetting is `main.py` in `src`, which will take data from `data/measure_diameter/input` as input and output into `data/measure_diameter/output`. 

### Method 1 (If you've created a virtual environment)
From your file explorer, double-click on `measure_diameter.bat` in this folder to run the script. This script will activate a virtual environment to access the necessary libraries. On the fourth line, it executes the main script via:
```bash
python src\main.py 
```
The file will default to accessing "0356_b_spectral_4cm.png" as written in `config.py`, unless otherwise specified. To change the input image, append the desired file name to the end of that line, as shown below:
```bash
python src\main.py 0529_b_spectral_3cm.png
```

### Method 2 (No virtual environment)
If you have the libaries installed in another manner, you can open a terminal, and from the root directory run:
```bash
python modules/measure_diameter/src/main.py
```
Again, if you need a specific file, apend the desired file name to thend of the line.

## What it Does
**Input**: Reads the image filename passed as an argument from `data/measure_diameter/input`. If no filename is provided, it uses `0356_b_spectral_4cm.png`.

**Output**: Writes diagnostic images to `data/measure_diameter/output`, named from the input image:
1. `{input_image_name}_cursor_preview.png`: The detected "Doppler cursor" (Doppler beam,  insonation line, and bound gates) overlaid on the image.
2. `{input_image_name}_green_mask.png`: A mask of the detected green cursor pixels.
3. `{input_image_name}_lumen_threshold_sweep.png`: A grid showing accepted lumen candidates and their cross-sections at different pixel-intensity thresholds. This image is written only if candidates are found. *The reported widths are in pixels and are not validated physical diameters.*

### Execution
1. **Load the Image.** Parse the optional input filename (or use the default), then load that image from the input directory. Stop with an error if a path is supplied instead of a filename or the image cannot be read.
2. **Detect the Cursor.** Detect green pixels and use them to identify the Doppler beam and fit the insonation line. Their intersection becomes the anchor point for the lumen search. Save the cursor preview and green mask, and print detection diagnostics.
3. **Search for Lumen Candidates.** Search a region around the anchor for dark lumen candidates. Sweep through several intensity thresholds, keeping components that contain the anchor and pass basic size checks.
4. **Report Results.** If no anchor or lumen candidates are found, stop with an error. Otherwise, create the threshold-sweep preview and print each candidate's cross-section width and other diagnostic measurements.


### Assumptions & Limits
This feasibility test assumes that:
- The Doppler cursor is visible and green enough for the configured color detection to find it.
- The vessel lumen is visible, and the intersection falls within a dark region that can be identified as a lumen candidate.

The threshold and component-size checks are heuristic, so image quality and contrast can affect whether candidates are found and what widths are reported. Widths are measured in pixels; without image calibration, they are not physical diameters. This prototype does not produce a validated measurement.

## Design Decision
**Use the Doppler cursor as a search anchor.** When users are using Doppler ultrasound to extract blood-flow information, a Doppler cursor is often present. Using its intersection with the insonation line narrows the area the program needs to search for the lumen. We initially explored detecting the vessel walls directly, but ultrasound image variation and irregular vessel boundaries make it difficult to find continuous walls reliably. The lumen may be a more robust target because it occupies a larger region than the vessel wall's narrow cross-section.

**Calculate the cursor intersection from fitted lines.** Initially, we masked the vertical Doppler beam and estimated its intersection with the insonation line from the midpoint between the two remaining stroke segments. For a small cursor, however, masking the beam can also erase a substantial part of the insonation line, making that midpoint inaccurate. The current approach detects the beam and the remaining insonation-stroke pixels from the green mask, fits the insonation line, and calculates where it crosses the beam.

**Determine an appropriate lumen threshold.** The current threshold sweep helps us inspect how candidate regions change with intensity, but more representative data is needed to choose an optimal threshold. We also need to define the error metric to minimize when evaluating how well a threshold captures the vessel lumen.

### Future Considerations
- Gather more ultrasound data to test with and determine optimal pixel intensity thresholds for lumen classification (define optimality in this scenario - research metrics for accuracy/error in ultrasound measrurements).
- Further explore lumen detection vs blood vessel wall detection - simulate for speed, accuracy, robustness.


