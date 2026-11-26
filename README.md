# Doppler Ultrasound Analysis — Throwaway Tests

## Project premise

This repository contains small experiments for exploring ways to analyze Doppler ultrasound screenshots and video frames. A **throwaway test** is a focused feasibility prototype: it helps us try an approach, learn what works, and identify limitations before deciding what belongs in a more complete system. These experiments may change or be replaced, and their outputs are not validated clinical measurements or diagnoses.

## Experiments

| Experiment | What it explores | Main entry point and module guide |
|---|---|---|
| Extract video frames | Save selected frames from one video or a directory of videos as image files. | [main.py](modules/extract_frames/src/main.py) · [README](modules/extract_frames/README.md) |
| Segment display windows | Identify the ultrasound display mode, extract the B-mode and active lower window, and calculate B-mode scale metadata. | [main.py](modules/segment_windows/src/main.py) · [README](modules/segment_windows/README.md) |
| ECG trace and R-peak candidates | Extract the green ECG trace from a screenshot and find image-based R-peak candidates. | [main.py](modules/ecg/src/main.py) · [README](modules/ecg/README.md) |
| Doppler waveform and envelope | Extract the white spectral Doppler waveform and its brightness-weighted envelope in pixel coordinates. | [main.py](modules/doppler_waveform/src/main.py) · [README](modules/doppler_waveform/README.md) |
| Velocity axis and parameters | Read the spectral Doppler velocity axis by OCR and fit cm/s per pixel; read the acquisition-parameter panel. | [main.py](modules/scale_ocr/src/main.py) · [README](modules/scale_ocr/README.md) |
| Circular vessel candidates | Detect possible circular vessel cross-sections in B-mode crops using classical image-processing methods. | [main.py](modules/detect_circular_vessels/src/main.py) · [README](modules/detect_circular_vessels/README.md) |
| Cursor-anchored lumen candidates | Use the Doppler cursor to anchor a search for dark lumen candidates and compare their pixel widths across thresholds. | [main.py](modules/measure_diameter/src/main.py) · [README](modules/measure_diameter/README.md) |

## Set up Python and libraries

Use **Python 3.14**, the version recorded in [`.python-version`](.python-version). Check which Python your terminal will use:

```bash
python --version
```

Create and activate a virtual environment from the repository root in Git Bash:

```bash
python -m venv .venv
source .venv/Scripts/activate
```

If `python` is not Python 3.14, and the Windows Python launcher is installed, create the environment with:

```bash
py -3.14 -m venv .venv
source .venv/Scripts/activate
```

Activation makes `python` and `pip` use the environment in `.venv`, keeping this project's libraries separate from other Python projects and your system installation. With the environment activated, install the pinned dependencies:

```bash
python -m pip install -r requirements.txt
```

The libraries in `requirements.txt` provide the shared image-processing, numerical, OCR, and notebook tools used by the experiments. The versions are pinned so contributors can use a consistent set of dependencies. The `segment_windows` and `scale_ocr` experiments also require the **Tesseract OCR application** to be installed separately and available on `PATH`; installing `pytesseract` from `requirements.txt` alone does not install Tesseract. On Windows, this can be installed from: https://github.com/UB-Mannheim/tesseract/wiki.

## Run an experiment

This page provides a quick setup and run summary. For a more detailed explanation of an experiment and to see whether it has a `.bat` file for easier launching, read its module README. The commands below run from the **repository root** with the virtual environment activated. Script arguments are optional unless noted; defaults read from each module's `data/<module>/input` directory and write results to its output directory. Use `--help` on a script to see its command-line options.

| Experiment | Run from Git Bash |
|---|---|
| Extract video frames | `python modules/extract_frames/src/main.py` |
| Segment display windows | `python modules/segment_windows/src/main.py` |
| Circular vessel candidates | `python modules/detect_circular_vessels/src/main.py` |
| Cursor-anchored lumen candidates | `python modules/measure_diameter/src/main.py` |
| ECG trace and R-peak candidates | `python modules/ecg/src/main.py` |
| Doppler waveform and envelope | `python modules/doppler_waveform/src/main.py` |
| Velocity axis and parameters | `python modules/scale_ocr/src/main.py` |

The image-analysis scripts accept optional input filenames or paths; some also accept command-line options. Run a script with `--help` to see its options. For example:

```bash
python modules/extract_frames/src/main.py --help
```