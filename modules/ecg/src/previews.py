"""Diagnostic images for one ECG extraction (the plots from scratch/ecg.ipynb)."""
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")  # write files only; works without a display (harness, CI)
import matplotlib.pyplot as plt

from config import GRAPH_SUFFIX, MASK_SUFFIX, OVERLAY_SUFFIX
from ecg_extractor import scaled_roi


def write_previews(out_stem: Path, img, mask, coords, ecg_y, present, r_peaks_x, r_peaks_y):
    """Write the ECG mask, the overlay on the screenshot and the standalone graph,
    each named `out_stem` plus a suffix."""
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_stem.with_name(out_stem.name + MASK_SUFFIX)), mask)
    x0, y0, x1, y1 = scaled_roi(img, "ecg")

    # Full-image overlay, zoomed to the ECG region for visual validation.
    fig, ax = plt.subplots(figsize=(13, 4.5))
    ax.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    if present:
        ax.plot(coords[:, 0], ecg_y, c="cyan", linewidth=1.2, label="Extracted ECG")
        if len(r_peaks_x):
            ax.scatter(r_peaks_x, r_peaks_y, c="red", s=10, marker="o",
                       edgecolors="white", linewidths=0.6, zorder=4,
                       label="R-peak candidates")
    else:
        ax.text(0.5, 0.5, "No reliable ECG signal detected",
                transform=ax.transAxes, ha="center", va="center", color="red")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y1, y0)  # original image pixel orientation
    ax.set_xlabel("Image x (pixels)")
    ax.set_ylabel("Image y (pixels)")
    ax.set_title("ECG extraction over original screenshot")
    if present:
        ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(out_stem.with_name(out_stem.name + OVERLAY_SUFFIX), dpi=160)
    plt.close(fig)

    # Standalone coordinate graph; same pixel coordinate convention.
    fig, ax = plt.subplots(figsize=(13, 4))
    if present:
        ax.plot(coords[:, 0], ecg_y, c="green", linewidth=1.4, label="ECG y-coordinates")
        if len(r_peaks_x):
            ax.scatter(r_peaks_x, r_peaks_y, color="red", s=10, zorder=4, label="R-peak candidates")
        ax.legend()
    else:
        ax.text(0.5, 0.5, "No reliable ECG signal detected",
                transform=ax.transAxes, ha="center", va="center")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y1, y0)
    ax.set_xlabel("Image x (pixels)")
    ax.set_ylabel("Image y (pixels)")
    ax.set_title("Extracted ECG waveform (image coordinates)")
    ax.grid(alpha=0.15)
    fig.tight_layout()
    fig.savefig(out_stem.with_name(out_stem.name + GRAPH_SUFFIX), dpi=160)
    plt.close(fig)
