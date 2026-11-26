"""Diagnostic images for one waveform extraction (the plot from scratch/waveform.ipynb)."""
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")  # write files only; works without a display (harness, CI)
import matplotlib.pyplot as plt

from config import MASK_SUFFIX, OVERLAY_SUFFIX
from waveform_extractor import scaled_roi


def write_previews(out_stem: Path, img, mask, envelope_coords):
    """Write the waveform mask and the envelope overlay, each named `out_stem` plus a suffix."""
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_stem.with_name(out_stem.name + MASK_SUFFIX)), mask)

    # Overlay in ORIGINAL image coordinates; no physical-unit conversion yet.
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    ax.plot(envelope_coords[:, 0], envelope_coords[:, 1], color="red", linewidth=1.5,
            label="Extracted envelope")
    x0, y0, x1, y1 = scaled_roi(img, "waveform")
    ax.set_xlim(x0 - 10, x1 + 10)
    ax.set_ylim(y1 + 15, y0 - 15)
    ax.set_title("Terason spectral Doppler: extracted envelope")
    ax.set_xlabel("X coordinate (pixels)")
    ax.set_ylabel("Y coordinate (pixels)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_stem.with_name(out_stem.name + OVERLAY_SUFFIX), dpi=160)
    plt.close(fig)
