# Scale OCR

Reads the spectral Doppler velocity axis and the acquisition-parameter panel of a Terason screenshot by OCR, and fits velocity (cm/s) against pixel row. The code in `src/` is ported from the root [`scale_ocr/test_ocr.ipynb`](../../scale_ocr/test_ocr.ipynb), whose [README](../../scale_ocr/README.md) explains the OCR method. The B-mode depth scale is not read here: `segment_windows` provides it in `windows.csv`.

## How to Run

Install the **Tesseract OCR application** and make sure it is on `PATH` (see the root README). Then, from the repository root, with the virtual environment activated:

```bash
python modules/scale_ocr/src/main.py
```

This processes every image in `data/scale_ocr/input/` and writes to `data/scale_ocr/output/`. Append an image path, a folder (searched recursively) or a filename inside `data/scale_ocr/input/` to process something else. A second argument sets the output folder, and `--no-previews` writes only the CSVs.

From Python, or from the harness, call `run(input, output, save_previews=True, progress=None)`. The harness's vessels pipeline runs it on the extracted video frames with `segment_windows`' `windows.csv`, processing only the frames that have a spectral window, with `save_previews=False`.

## What it Does

**Input**: One of:
- Full screenshots: an image, a folder of images, or a filename inside `data/scale_ocr/input` (with no argument, every image there).
- Full frames plus `segment_windows`' `windows.csv`: a folder holding `windows.csv` next to the frames, or a folder with two subfolders, one holding `windows.csv` and the other the frames (the layout the harness passes). Only frames with a `spectral` window are processed.

**Output**: Written to the output folder, one row per image:

| File | Contents |
|---|---|
| `velocity_scale.csv` | `image`, `cm_s_per_px`, `cm_s_at_y0`, `zero_y`, `n_labels`, `max_residual_cm_s`, `labels`. Velocity (cm/s) = `cm_s_per_px` × y + `cm_s_at_y0` for a full-frame pixel row y; `zero_y` is the row of 0 cm/s; `labels` lists each tick label read as `value@y`. Images whose axis can't be fitted are left out and listed at the end of the log. |
| `params.csv` | `image` plus each parameter-panel readout found: `depth_cm`, `frame_rate`, `heart_rate`, `sv_size_mm`, `sv_depth_cm`, `freq_mhz`, `prf_khz`, `angle_deg`, `mi`. Blank where it wasn't read. |

`cm_s_per_px` is negative on a normal display and positive when the spectrum is shown inverted (e.g. `half_b_half_doppler.png`, labelled -180 at the top). Unless `--no-previews` is given, it also writes `{image}_ocr_debug.png` per image: the OCR regions (yellow) and every tick label read (red).

### Execution

1.  **Read the velocity labels:** Crop the velocity-axis ROI, binarise it,
    and run Tesseract in three page-segmentation modes, keeping the most
    confident reading at each position.
2.  **Reject outliers:** Tick labels are evenly spaced, so readings that
    sit more than 3 px off the fitted line are dropped one at a time.
3.  **Fit and recover:** Fit value = a·y + b, predict where any missing
    label (including 0) should be, re-read a thin strip there, and refit.
4.  **Read the parameter panel:** OCR the right-hand panel and pull each
    value out with a regular expression.
5.  **Save results:** Add the image's rows to the CSVs and, with
    previews, write the debug image.

### Assumptions & Limits

The ROIs are fixed rectangles on the 1024 × 768 Terason layout. The fit is only as good as the labels OCR reads; check `n_labels` and `max_residual_cm_s`. The velocity scale is not yet validated against a known reference.
