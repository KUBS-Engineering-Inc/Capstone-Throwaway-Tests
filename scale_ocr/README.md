# Scale OCR

Reads the scales off an ultrasound screenshot using OCR so we can turn pixel positions into real units (depth in cm for the B-mode, velocity in cm/s for the Doppler spectrum). Everything is in `test_ocr.ipynb`, tested on two sample frames in `assets/`.

## Folder Contents

| File                             | What it is                                                                                     |
| -------------------------------- | ---------------------------------------------------------------------------------------------- |
| `test_ocr.ipynb`                 | The notebook with all the OCR code and tests                                                   |
| `assets/full_b_mode.png`         | A B-mode only frame, where the B-mode image takes up the full height of the screen             |
| `assets/half_b_half_doppler.png` | A spectral view, where the B-mode is on the top half and the Doppler spectrum is on the bottom |
| The root `requirements.txt`      | Python packages the notebook needs, found one folder level above                               |

## How to Run

1. **Install Tesseract.** `pytesseract` is just a wrapper, so the Tesseract OCR engine itself has to be installed on your machine and on your `PATH`. Instructions here: https://github.com/KUBS-Engineering-Inc/Capstone-Design-History-File/blob/main/00_Admin/ToolsInstallationGuide.md
2. **Set up the Python environment.** The project uses Python 3.14 (see `.python-version` at the repo root).
   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # Windows
   source .venv/bin/activate       # macOS / Linux
   pip install -r requirements.txt
   ```
3. **Open `test_ocr.ipynb`** in Jupyter or VS Code with that environment as the kernel and run the cells top to bottom. The image paths are built from the current working directory (`Path.cwd() / "assets"`), so the notebook needs to be run from inside this folder.

The notebook prints the parsed values for each image and shows a debug overlay with the regions of interest (yellow) and every number that OCR picked up (red).

## What it Does

At its core, this is just OCR on the scales of the image. The notebook is split into a few sections:

**Regions of interest.** Each part of the screen we care about is defined as a fixed box on a 1024x768 reference frame:

| Region               | What's in it                                                                                       |
| -------------------- | -------------------------------------------------------------------------------------------------- |
| `header`             | Date, preset name, and device name along the top                                                   |
| `params`             | The settings text on the right (MI, Depth, SV size, PRF, Angle, etc.)                              |
| `depth_scale`        | The cyan depth numbers (0 to 4 cm) for the spectral view, where the B-mode is only half the height |
| `depth_scale_b_only` | The same depth numbers for the B-mode only view, where the scale runs the full height              |
| `velocity_axis`      | The Doppler velocity labels on the left (-180 to 60 cm/s)                                          |
| `footer`             | The bottom status bar                                                                              |

If a frame comes in at a different resolution, the boxes get rescaled to match it.

**Preprocessing.** Before anything goes to Tesseract, each crop is upscaled 3x since Tesseract does a lot better on bigger text. There are two preprocessing paths:

- `prep_light_on_dark` is for the white/grey text. It converts to grayscale, blurs a bit, thresholds with Otsu, and flips it to black text on white.
- `prep_cyan` is for the cyan depth numbers. It pulls out just the cyan pixels using an HSV color mask so the grey ultrasound image behind it gets ignored, thickens the thin digits slightly, and then strips out the long tick marks next to each number (`strip_lines`) since those were making Tesseract drop the digits.

**Reading a scale.** `read_axis` is what actually turns a scale into a pixel-to-unit conversion:

1. Run Tesseract with a few different page segmentation modes and keep the most confident reading at each spot (`ocr_words_multi`). Single characters like a lone `0` tend to get missed by one mode but caught by another.
2. Throw out any number that doesn't sit on a straight line with the others (`reject_outliers`), like a `0` that got misread as a `6`.
3. Fit a line `value = a * y + b` through the remaining labels (`fit_axis`).
4. Since the labels are evenly spaced, use that fit to predict where any missing label should be, then re-OCR just a thin strip around that spot to try and recover it (`recover_missing`). The `0` at the top of the depth scale is almost always the one that gets recovered this way.

**Parameters and header.** `read_params` OCRs the settings panel and pulls values out with regex (depth, frame rate, heart rate, SV size, SV depth, frequency, PRF, angle, MI). `read_header` just returns the raw header text.

**Sanity check.** The depth fit from the scale numbers gets compared against the "Depth 4 cm" readout from the settings panel to make sure they agree.

**Results on the sample images.**

| Image                                | Scale    | Result                                                     |
| ------------------------------------ | -------- | ---------------------------------------------------------- |
| Spectral (half B-mode, half Doppler) | Depth    | 0 to 4 cm read, ~71.8 px per cm, max residual 0.01         |
| Spectral (half B-mode, half Doppler) | Velocity | -180 to 60 cm/s read, ~1.03 px per cm/s, max residual 0.00 |
| B-mode only                          | Depth    | 0 to 4 cm read, ~145.6 px per cm, max residual 0.00        |

In both images the depth check lines up with the "Depth 4 cm" readout. The B-mode only image doesn't have the extra Doppler settings (SV size, PRF, Angle, etc.), so only depth, frame rate, and MI come back from the params panel, which is expected.

The last section of the notebook starts on a simpler idea: only read the numbers at the two ends of the scale and attach them to the scale line, then interpolate the depth for every pixel in between. Right now that section just draws the region and runs the preprocessing on it, so it isn't finished yet.

## Design Decision

The first idea we thought about was to detect the numbers manually by looking for their characteristics (shape, color, size, being next to a tick mark) across the whole image, and then figuring out which ones belonged to which scale. The problem is that an ultrasound screenshot has a lot going on: the B-mode image itself, the Doppler spectrum, the ECG trace, the settings text, and the buttons along the bottom all have things that look like digits or lines. Searching the whole image would mean we'd have to sort out what's actually a scale label from everything else, which adds a lot of room for mistakes.

Instead, we decided to use pre-defined boundaries for each section of the screen. Since the scanner always puts things in the same place for a given layout, we can just crop straight to where each scale is and only run OCR there. That keeps the OCR focused on the right numbers and makes the results a lot more reliable.

The catch is that the layout changes depending on the mode, so one set of boundaries doesn't work for everything:

- In the **spectral view**, the Doppler spectrum sits on the bottom half of the screen and the B-mode is squished into the top half, so the depth scale only runs about half the height of the screen (`depth_scale`). This view also has the velocity axis on the left that needs its own region (`velocity_axis`).
- In the **B-mode only** view, the B-mode takes up the full height, so the depth scale runs the whole way down (`depth_scale_b_only`) and there is no velocity axis at all.

So we ended up with different boundaries for each layout, and `read_depth_scale` takes an `is_bmode_only` flag to pick which depth region to use. You can see this in the results too: the same 0 to 4 cm scale comes out to about 72 px per cm in the spectral view and about 146 px per cm in the B-mode only view, which is roughly double since it's using twice the height.
