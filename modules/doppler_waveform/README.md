# How to Run

## Doppler waveform and envelope

Open `waveform.ipynb`. By default, it reads
`data/ecg/input/doppler_envelope.png` and saves results to `data/doppler_waveform/output`.

The test cell calls:

``` python
results = main(
    input_path=waveform_img_path,
    output_path=output_dir,
)
```

The same function can be called with another image and output folder:

``` python
from pathlib import Path

results = main(
    input_path=Path("data/ecg/input/doppler_envelope.png"),
    output_path=Path("data/doppler_waveform/output"),
)
```

# What it Does

## Doppler waveform and envelope extraction

The Doppler notebook extracts the white spectral Doppler trace from a
Terason screenshot and calculates its upper envelope in image-pixel
coordinates.

1.  **Load and crop:** Read the screenshot and crop the Doppler region
    of interest (ROI). The ROI is defined relative to a 1024 × 768
    reference image and scaled to the input dimensions.
2.  **Create a waveform mask:** Convert the cropped ROI to grayscale.
    Pixels brighter than `THRESHOLD` are classified as foreground. A 2 ×
    2 morphological opening removes small isolated speckles.
3.  **Extract waveform coordinates:** Record every foreground pixel as
    an `(x, y)` pair in full-image pixel coordinates.
4.  **Extract the envelope:** For each ROI column, select the smallest
    detected y-coordinate. Since image y-coordinates increase downward,
    this is the uppermost detected white pixel.
5.  **Handle missing columns:** Linearly interpolate only internal gaps
    of up to `MAX_INTERPOLATION_GAP` columns (5 by default). Longer gaps
    and gaps at either end remain `NaN`.
6.  **Save results:** Write coordinate CSV files, a binary mask image,
    and an overlay showing the envelope on the original screenshot.

The `main()` function returns:

-   `waveform_coords`: all detected waveform `(x, y)` pixel coordinates.
-   `envelope_coords`: envelope `(x, y)` coordinates; y is `NaN` where
    long or edge gaps remain.
-   `envelope_y`: envelope y-coordinates only.
-   `waveform_mask`: binary mask of the cropped Doppler ROI.
-   `valid_columns`: Boolean array marking columns where waveform pixels
    were directly detected.
-   `interpolated_columns`: Boolean array marking values filled by
    short-gap interpolation.

Files saved in `outputs/waveform/`:

  -----------------------------------------------------------------------
  File                                Contents
  ----------------------------------- -----------------------------------
  `waveform_coordinates.csv`          Detected waveform coordinates
                                      (`x_pixel`, `y_pixel`)

  `envelope_coordinates.csv`          Envelope coordinates (`x_pixel`,
                                      `y_pixel`)

  `envelope_y.csv`                    Envelope y-coordinate for each ROI
                                      column

  `waveform_mask.png`                 Binary Doppler mask

  `envelope_overlay.png`              Original screenshot with the
                                      extracted envelope overlaid
  -----------------------------------------------------------------------

# Design Decision

## Doppler waveform and envelope

-   **Grayscale thresholding:** The Doppler trace is bright/gray against
    a dark graph background, so grayscale thresholding is used instead
    of colour-specific detection. Adjust `THRESHOLD` if screenshot
    brightness changes.
-   **Morphological opening:** A small 2 × 2 kernel removes isolated
    foreground speckles while aiming to preserve the waveform.
-   **Uppermost pixel per column:** The envelope is defined as the
    smallest y-coordinate in each column because the desired output is
    the upper boundary of the spectral Doppler trace.
-   **Short-gap-only interpolation:** `MAX_INTERPOLATION_GAP = 5`
    bridges only short internal gaps with detected points on both sides.
    Longer gaps and gaps at the ROI edges remain `NaN` rather than
    estimating an envelope across a region with insufficient detected
    signal.
-   **Detection tracking:** `valid_columns` marks directly detected
    columns. `interpolated_columns` separately marks estimated values.
    Later processing can distinguish detected, estimated, and missing
    data.
-   **Pixel coordinates only:** The notebook does not convert image
    coordinates into time, velocity, or other physical units. OCR and
    calibration are handled separately.