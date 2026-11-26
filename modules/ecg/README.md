# ECG

Extracts the green ECG trace from a Terason screenshot as pixel coordinates and finds image-based R-peak candidates. The code is in `src/`; `scratch/ecg.ipynb` is the notebook it was developed in.

## How to Run

From the repository root, with the virtual environment activated:

```bash
python modules/ecg/src/main.py
```

This processes every image in `data/ecg/input/` and writes to `data/ecg/output/`. Append an image path, a folder (searched recursively) or a filename inside `data/ecg/input/` to process something else. A second argument sets the output folder, and `--no-previews` writes only the CSVs.

From Python, or from the harness, call `run(input, output, save_previews=True, progress=None)`. The harness's vessels pipeline runs it on the extracted video frames with `segment_windows`' `windows.csv`, processing only the frames that have a spectral window, with `save_previews=False`.

## What it Does

**Input**: One of:
- Full screenshots: an image, a folder of images, or a filename inside `data/ecg/input` (with no argument, every image there).
- Full frames plus `segment_windows`' `windows.csv`: a folder holding `windows.csv` next to the frames, or a folder with two subfolders, one holding `windows.csv` and the other the frames (the layout the harness passes). Only frames with a `spectral` window are processed; the ECG is read from the full frame, not the window crop.

**Output**: Written to the output folder, one set of rows per image:

| File | Contents |
|---|---|
| `ecg_summary.csv` | `image`, `ecg_present`, `coverage`, `n_r_peaks` |
| `ecg_trace.csv` | `image`, `x`, `y`: one row per column of the ECG region. `y` is blank where no trace was found. |
| `r_peaks.csv` | `image`, `x`, `y`: one row per R-peak candidate |

Coordinates are full-frame pixels (origin top left). Unless `--no-previews` is given, it also writes per image `{image}_ecg_mask.png` (detected green pixels in the ECG region), `{image}_ecg_overlay.png` (trace and candidates over the screenshot) and `{image}_ecg_graph.png` (the trace on its own).

### Execution

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
    (70% by default), mark the ECG as absent and set every y-coordinate
    to `NaN`.
5.  **Leave gaps empty:** Columns without green pixels (such as the
    sweep refresh bar) stay `NaN`; nothing is interpolated.
6.  **Detect R-peak candidates:** Split the trace into its unbroken
    segments and process each separately, so a gap never joins two parts
    of the trace or produces a peak on a beat cut off by the gap. Within
    a segment, apply a median filter for detection, then invert the
    y-coordinates relative to the trace's median so upward ECG
    deflections become maxima. `scipy.signal.find_peaks()` applies
    prominence, distance, and width constraints.
7.  **Refine candidate positions:** For each candidate, search within ±5
    samples in the unsmoothed segment and select the smallest
    y-coordinate.
8.  **Save results:** Add the image's rows to the CSVs and, with
    previews, write the mask, overlay and graph.

## Design Decision

### ECG waveform and R-peak extraction

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
-   **No interpolation across gaps:** Missing columns are left empty
    rather than filled with made-up coordinates, and peaks are found per
    unbroken segment.
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
-   **Two-peak safeguard implementation note:** `config.py` defines
    `MIN_PRESENT_PEAKS = 2`, but `detect_r_peaks()` does not currently
    check that at least two candidates were found. As written, it can
    return one candidate. Add an explicit candidate-count check if the
    two-peak requirement is intended.
-   **Not a clinical interpretation:** R-peaks are image-shape
    candidates only, not clinically validated detections or a diagnostic
    assessment.
-   **Pixel coordinates only:** No OCR, time calibration, or
    physiological measurement conversion is performed. The coordinates
    can be calibrated in a later processing stage.
