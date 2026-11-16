# How to Run

## ECG waveform and R-peak candidates

Open `ecg.ipynb`. By default, it reads `data/ecg/input/ecg_wave.png` and
saves results to `data/ecg/output/`.

The test cell calls:

``` python
results = main(
    input_path=ecg_img_path,
    output_path=output_dir,
)
```

The same function can be called with another image and output folder:

``` python
from pathlib import Path

results = main(
    input_path=Path("data/ecg/input/ecg_wave.png"),
    output_path=Path("data/ecg/output"),
)
```

# What it Does

## ECG waveform and R-peak extraction

The ECG notebook extracts the green ECG trace from a Terason screenshot,
returns its y-coordinates, and identifies image-based R-peak candidates.

1.  **Load and crop:** Read the screenshot and crop the ECG ROI. The ROI
    is defined relative to a 1024 × 768 reference image and scaled to
    the input dimensions.
2.  **Detect green pixels:** Include pixels whose green channel exceeds
    `MIN_GREEN` and is sufficiently greater than both the red and blue
    channels.
3.  **Extract ECG coordinates:** For each ROI column containing green
    pixels, select the smallest y-coordinate. This follows the upper
    edge of the detected green trace. Coordinates refer to the full
    screenshot.
4.  **Check trace coverage:** Calculate the fraction of ROI columns
    containing green pixels. If coverage is below `MIN_TRACE_COVERAGE`
    (70% by default), mark the ECG as absent and set the y-coordinate
    array to `NaN`.
5.  **Fill missing coordinates when coverage passes:** If coverage is
    sufficient, `np.interp()` fills missing columns. In the current
    implementation this fills all missing columns, including long
    internal gaps and leading/trailing columns; it is not limited to
    short gaps.
6.  **Detect R-peak candidates:** Apply a median filter for detection,
    then invert the y-coordinate series relative to its median so upward
    ECG deflections become numerical maxima. `scipy.signal.find_peaks()`
    applies prominence, distance, and width constraints.
7.  **Refine candidate positions:** For each candidate, search within ±5
    samples in the unsmoothed extracted ECG series and select the
    smallest y-coordinate.
8.  **Save results:** Write ECG coordinate CSV files, the green-pixel
    mask, a standalone ECG graph, and an overlay on the original
    screenshot with candidate peaks marked.

The `main()` function returns:

-   `ecg_mask`: binary mask of detected green pixels in the cropped ECG
    ROI.
-   `ecg_coords`: ECG `(x, y)` coordinates in full-image pixel
    coordinates.
-   `ecg_y`: ECG y-coordinate series.
-   `valid_columns`: Boolean array marking columns where green pixels
    were directly detected, before interpolation.
-   `ecg_present`: whether the green-pixel coverage threshold was met.
-   `r_peaks_x`: full-image x-coordinates of R-peak candidates.
-   `r_peaks_y`: y-coordinates of R-peak candidates.
-   `coverage`: fraction of ECG ROI columns containing detected green
    pixels.

Files saved in `data/ecg/output/`:

  -----------------------------------------------------------------------
  File                                Contents
  ----------------------------------- -----------------------------------
  `ecg_y.csv`                         ECG y-coordinate for each ROI
                                      column

  `ecg_coordinates.csv`               ECG coordinates (`x_pixel`,
                                      `y_pixel`)

  `r_peaks.csv`                       Detected R-peak candidate
                                      coordinates

  `ecg_mask.png`                      Binary mask of detected green
                                      pixels

  `ecg_overlay.png`                   Original screenshot with ECG trace
                                      and candidates overlaid

  `ecg_graph.png`                     Standalone ECG coordinate graph
  -----------------------------------------------------------------------

# Design Decision

## ECG waveform and R-peak extraction

-   **Colour-dominance detection:** Green-channel thresholds are used
    because the ECG trace is green. Requiring green to exceed red and
    blue helps distinguish the trace from other image content.
-   **ROI-based processing:** Only the ECG region is analysed, limiting
    interference from the white Doppler waveform and other interface
    elements.
-   **Coverage safeguard:** The ECG is accepted only when at least 70%
    of columns in the ECG ROI contain detected green pixels. This is a
    trace-coverage check, not proof that the detected pixels form a
    valid ECG.
-   **Upper-edge coordinate selection:** The smallest green-pixel
    y-coordinate is selected in each column. This follows the upper edge
    of the rendered trace, not necessarily its centreline.
-   **Smoothing only for detection:** A small median filter reduces
    coordinate fluctuations before peak detection. The extracted
    unsmoothed coordinates are retained for refining candidate
    positions.
-   **Upward-peak transformation:** Image y increases downward, so
    upward ECG spikes have smaller y-values. Subtracting the smoothed
    series from its median turns these upward deflections into maxima
    for `find_peaks()`.
-   **Constrained peak candidates:** Prominence, minimum spacing, and
    width limits reject some small fluctuations and implausibly shaped
    candidates. Each candidate is then refined locally using the
    smallest unsmoothed y-coordinate.
-   **Two-peak safeguard implementation note:** The notebook defines
    `MIN_PRESENT_PEAKS = 2` and the detector docstring mentions a
    two-peak safeguard, but the uploaded `detect_r_peaks()`
    implementation does not currently check that at least two candidates
    were found. As written, it can return one candidate. Add an explicit
    candidate-count check if the two-peak requirement is intended.
-   **Not a clinical interpretation:** R-peaks are image-shape
    candidates only, not clinically validated detections or a diagnostic
    assessment.
-   **Pixel coordinates only:** No OCR, time calibration, or
    physiological measurement conversion is performed. The coordinates
    can be calibrated in a later processing stage.
