# Doppler Waveform

Extracts the white spectral Doppler trace from a Terason screenshot and calculates an envelope (the brightness-weighted mean row of the trace in each column), in image-pixel coordinates. The code is in `src/`; `scratch/waveform.ipynb` is the notebook it was developed in.

## How to Run

From the repository root, with the virtual environment activated:

```bash
python modules/doppler_waveform/src/main.py
```

This processes every image in `data/doppler_waveform/input/` and writes to `data/doppler_waveform/output/`. Append an image path, a folder (searched recursively) or a filename inside `data/doppler_waveform/input/` to process something else. A second argument sets the output folder, and `--no-previews` writes only the CSVs.

From Python, or from the harness, call `run(input, output, save_previews=True, progress=None)`. The harness's vessels pipeline runs it on the extracted video frames with `segment_windows`' `windows.csv`, processing only the frames that have a spectral window, with `save_previews=False`.

## What it Does

**Input**: One of:
- Full screenshots: an image, a folder of images, or a filename inside `data/doppler_waveform/input` (with no argument, every image there).
- Full frames plus `segment_windows`' `windows.csv`: a folder holding `windows.csv` next to the frames, or a folder with two subfolders, one holding `windows.csv` and the other the frames (the layout the harness passes). Only frames with a `spectral` window are processed; the waveform is read from the full frame, not the window crop.

**Output**: Written to the output folder, one set of rows per image:

| File | Contents |
|---|---|
| `envelope.csv` | `image`, `x`, `y`, `detected`, `interpolated`: one row per column of the waveform region. `y` is blank where the gap was too long to fill. |
| `waveform_summary.csv` | `image`, `columns`, `detected_columns`, `interpolated_columns`, `missing_columns`, `waveform_pixels` |

Coordinates are full-frame pixels (origin top left). Images with no waveform are skipped and listed at the end of the log. Unless `--no-previews` is given, it also writes per image `{image}_waveform_mask.png` (the binary waveform mask) and `{image}_envelope_overlay.png` (the envelope over the screenshot).

### Execution

1.  **Load and crop:** Read the screenshot and crop the Doppler region
    of interest (ROI). The ROI is defined relative to a 1024 × 768
    reference image and scaled to the input dimensions.
2.  **Create a waveform mask:** Convert the cropped ROI to grayscale.
    Pixels brighter than `THRESHOLD` are classified as foreground. A 2 ×
    2 morphological opening removes small isolated speckles.
3.  **Extract the envelope:** For each ROI column, take the mean
    y-coordinate of the foreground pixels, weighted by their grayscale
    brightness.
4.  **Handle missing columns:** Linearly interpolate only internal gaps
    of up to `MAX_INTERPOLATION_GAP` columns (5 by default). Longer gaps
    and gaps at either end remain `NaN`.
5.  **Optional smoothing:** With `MEDIAN_KERNEL` above 1, median-smooth
    each unbroken run separately. It is 1 (off) by default.
6.  **Save results:** Add the image's rows to the CSVs and, with
    previews, write the mask and overlay.

## Design Decision

### Doppler waveform and envelope

-   **Grayscale thresholding:** The Doppler trace is bright/gray against
    a dark graph background, so grayscale thresholding is used instead
    of colour-specific detection. Adjust `THRESHOLD` if screenshot
    brightness changes.
-   **Morphological opening:** A small 2 × 2 kernel removes isolated
    foreground speckles while aiming to preserve the waveform.
-   **Brightness-weighted mean per column:** Each column's value is the
    brightness-weighted mean row of the trace, not its uppermost pixel,
    so it is not the peak-velocity envelope.
-   **Short-gap-only interpolation:** `MAX_INTERPOLATION_GAP = 5`
    bridges only short internal gaps with detected points on both sides.
    Longer gaps and gaps at the ROI edges remain `NaN` rather than
    estimating an envelope across a region with insufficient detected
    signal.
-   **Detection tracking:** The `detected` column marks directly
    detected columns and `interpolated` marks estimated values, so later
    processing can distinguish detected, estimated, and missing data.
-   **Pixel coordinates only:** This stage does not convert image
    coordinates into time, velocity, or other physical units. The
    `scale_ocr` stage fits the velocity axis separately.
