"""Classify Doppler ultrasound images as transverse or longitudinal vessel views.

Usage:
    python modules/classify_view/src/main.py [INPUT] [OUTPUT] [--show]

INPUT is an image, or a directory of images, already cropped to the B-mode view
(default: data/classify_view/input/).
OUTPUT is a directory (default: data/classify_view/output/, created if needed). Every input image is
saved there with the overlay drawn on it (same filename): the view label and
confidence in the top-left, and the deciding region outlined in yellow. OUTPUT/views.csv has
one row per image: view (transverse | longitudinal | unknown), confidence, and
the two evidence scores.
--show also displays each overlay in a window (any key: next, q: quit).

Method (classical OpenCV, no training):
  A vessel lumen is anechoic (dark) with bright walls. Dark regions are found
  by sweeping a darkness threshold, then judged by shape:
    longitudinal - a long, roughly horizontal dark band with bright walls
                   (it may run off the left/right edge of the image);
    transverse   - a sizeable round/elliptical dark region with a bright wall
                   ring that does not touch the image edge.
  The stronger evidence wins; if neither is convincing the view is "unknown".
"""
import argparse
import csv
import math
from pathlib import Path

import cv2
import numpy as np

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "classify_view"  # modules/classify_view/src/main.py -> repo root
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
WORK_SIZE = 300  # images are resized so their shorter side is this many px
THRESHOLDS = range(10, 95, 5)
MIN_EVIDENCE = 0.35  # below this for both views -> "unknown"


def clean_view(bgr):
    """Return (gray, flow, clipped_flow).

    gray has overlays inpainted and colour-flow pixels set to 0 (lumen); flow is
    the colour-flow mask; clipped_flow is the part of it cut off by the ROI box.
    """
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    colored = (sat > 90) & (val > 60)
    # OpenCV hue is 0..179. Doppler flow maps are red/orange/yellow and blue;
    # green (35-85) and cyan (85-100) are cursor / ROI-box overlays.
    flow_hue = (hue < 35) | (hue > 100)
    ell5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    flow = cv2.morphologyEx((colored & flow_hue).astype(np.uint8), cv2.MORPH_OPEN, ell5)
    overlay = cv2.dilate((colored & (flow == 0)).astype(np.uint8), ell5)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    if overlay.any():
        gray = cv2.inpaint(gray, overlay, 5, cv2.INPAINT_TELEA)
    gray[flow > 0] = 0
    # Flow blobs that touch an overlay line are cut off by the colour ROI box, so
    # their outline is the box's, not the vessel's.
    n, labels = cv2.connectedComponents(flow)
    touching = np.unique(labels[(cv2.dilate(overlay, ell5) > 0) & (flow > 0)])
    clipped = np.isin(labels, touching[touching > 0]).astype(np.uint8)
    return gray, flow, clipped


def measure(contour, smooth, flow, clipped):
    """Shape and contrast features for one dark region."""
    h, w = smooth.shape
    area = cv2.contourArea(contour)
    hull = cv2.convexHull(contour)
    hull_area = cv2.contourArea(hull)
    hull_perim = cv2.arcLength(hull, True)
    (cx, cy), (d1, d2), angle = cv2.fitEllipse(contour)
    major, minor = max(d1, d2), min(d1, d2)
    major_angle = (angle if d1 >= d2 else angle + 90) % 180
    x, y, bw, bh = cv2.boundingRect(contour)
    reg = dict(
        contour=contour,
        radius=math.sqrt(area / math.pi),
        area=float(area),
        major=float(major),
        minor=float(minor),
        aspect=float(minor / major) if major else 0.0,
        tilt=float(min(major_angle, 180 - major_angle)),  # major axis vs horizontal, 0..90
        span=bw / w,  # horizontal extent as a fraction of image width
        circularity=float(4 * math.pi * hull_area / hull_perim ** 2) if hull_perim else 0.0,
        solidity=float(area / hull_area) if hull_area else 0.0,
        touches_lr=x <= 1 or x + bw >= w - 1,
        touches_tb=y <= 1 or y + bh >= h - 1,
        contrast=0.0,
        interior=255.0,
        flow_frac=0.0,
        clipped_frac=0.0,
    )
    if transverse_shape(reg) == 0 and longitudinal_shape(reg) == 0:
        return reg  # cannot be evidence for either view; skip the costly contrast step

    # Wall ring: a band just outside the region (thickness scales with region size).
    k = max(3, int(0.4 * min(math.sqrt(area / math.pi), minor / 2 + 1)) * 2 + 1)
    # Work in a padded crop around the region rather than the whole image.
    x0, y0 = max(0, x - k), max(0, y - k)
    x1, y1 = min(w, x + bw + k), min(h, y + bh + k)
    inside = np.zeros((y1 - y0, x1 - x0), np.uint8)
    cv2.drawContours(inside, [contour - [x0, y0]], -1, 1, cv2.FILLED)
    # Ring = pixels within k/2 of the region (distance transform is O(n) for any ring width).
    ring = (cv2.distanceTransform(1 - inside, cv2.DIST_L2, 3) <= k / 2) & (inside == 0)
    patch = smooth[y0:y1, x0:x1]
    interior = float(patch[inside > 0].mean())
    wall = float(patch[ring > 0].mean()) if ring.any() else interior

    reg["interior"] = interior
    reg["contrast"] = wall - interior
    reg["flow_frac"] = float(flow[y0:y1, x0:x1][inside > 0].mean())
    reg["clipped_frac"] = float(clipped[y0:y1, x0:x1][inside > 0].mean())
    return reg


def dark_regions(gray, flow, clipped, min_area_frac=0.002):
    """Every dark region found at any threshold level, measured. Yields dicts."""
    h, w = gray.shape
    smooth = cv2.GaussianBlur(cv2.medianBlur(gray, 5), (0, 0), 2)
    ell = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    for t in THRESHOLDS:
        mask = cv2.morphologyEx((smooth < t).astype(np.uint8), cv2.MORPH_OPEN, ell)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        for c in contours:
            if len(c) >= 5 and cv2.contourArea(c) >= min_area_frac * h * w:
                yield measure(c, smooth, flow, clipped)


def contrast_term(reg):
    """0..1: how much brighter the wall is than the lumen."""
    if reg["interior"] >= 0.6 * (reg["interior"] + reg["contrast"]):  # lumen must be < 60% of wall
        return 0.0
    return ramp(reg["contrast"], 10, 40)


def transverse_evidence(reg, min_dim):
    """0..1: a sizeable, round, walled dark region away from the image edges."""
    if reg["touches_lr"] or reg["touches_tb"] or reg["solidity"] < 0.85 or reg["clipped_frac"] > 0.5:
        return 0.0
    if reg["radius"] < 0.06 * min_dim:  # tiny round blobs show up in longitudinal views too
        return 0.0
    return transverse_shape(reg) * contrast_term(reg)


def ramp(v, lo, hi):
    """0 at lo, 1 at hi, linear in between."""
    return min(1.0, max(0.0, (v - lo) / (hi - lo)))


def transverse_shape(reg):
    """0..1 roundness. Transverse lumens are often elliptical, so aspect 0.6 already counts as round."""
    return ramp(reg["aspect"], 0.35, 0.6) * ramp(reg["circularity"], 0.65, 0.85)


def longitudinal_shape(reg):
    """0..1 elongation along the image width."""
    if reg["tilt"] > 30 or reg["aspect"] > 0.35:
        return 0.0
    return ramp(reg["span"], 0.2, 0.5) * ramp(reg["solidity"], 0.5, 0.85)


def longitudinal_evidence(reg):
    """0..1: a long, roughly horizontal, walled dark band."""
    if reg["touches_tb"]:
        return 0.0
    # A band filled with colour flow is a lumen regardless of how bright its wall looks.
    # (Not applied to transverse: flow blobs clipped by the colour box can look round.)
    walled = 1.0 if reg["flow_frac"] > 0.5 else contrast_term(reg)
    return longitudinal_shape(reg) * walled


def classify(image):
    """Return dict(view, confidence, transverse, longitudinal, contour, scale)."""
    s = WORK_SIZE / min(image.shape[:2])
    work = cv2.resize(image, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    gray, flow, clipped = clean_view(work)
    min_dim = min(gray.shape)
    best = {"transverse": (0.0, None), "longitudinal": (0.0, None)}
    for reg in dark_regions(gray, flow, clipped):
        for view, ev in (("transverse", transverse_evidence(reg, min_dim)),
                         ("longitudinal", longitudinal_evidence(reg))):
            if ev > best[view][0]:
                best[view] = (ev, reg["contour"])
    t, l = best["transverse"][0], best["longitudinal"][0]
    if max(t, l) < MIN_EVIDENCE:
        view, conf, contour = "unknown", 1 - max(t, l) / MIN_EVIDENCE, None
    else:
        view = "transverse" if t > l else "longitudinal"
        conf = abs(t - l) / max(t, l)  # 1 = only one view has evidence, 0 = tie
        contour = best[view][1]
    if contour is not None:
        contour = np.round(contour / s).astype(np.int32)
    return dict(view=view, confidence=round(conf, 3), transverse=round(t, 3),
                longitudinal=round(l, 3), contour=contour)


def annotate(image, result):
    out = image.copy()
    if result["contour"] is not None:
        cv2.drawContours(out, [result["contour"]], -1, (0, 255, 255), 2)
    label = f"{result['view']} ({result['confidence']:.2f})"
    cv2.putText(out, label, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(out, label, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1, cv2.LINE_AA)
    return out


def show_image(title, image):
    """Display an image; returns False if the user pressed q/Esc to stop."""
    cv2.imshow("result", image)
    cv2.setWindowTitle("result", f"{title}  (any key: next, q: quit)")
    return cv2.waitKey(0) & 0xFF not in (ord("q"), 27)


def list_images(path):
    path = Path(path)
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    raise FileNotFoundError(f"Input not found: {path}")


def run(input, output, show=False):
    """Classify every image under `input`; write overlays and views.csv to `output`.

    Returns {"transverse": n, "longitudinal": n, "unknown": n}.
    """
    images = list_images(input)
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {"transverse": 0, "longitudinal": 0, "unknown": 0}

    with open(out_dir / "views.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["image", "view", "confidence", "transverse", "longitudinal"],
                                extrasaction="ignore")
        writer.writeheader()
        for img_path in images:
            image = cv2.imread(str(img_path))
            if image is None:
                print(f"Skipping unreadable image: {img_path}")
                continue
            result = classify(image)
            writer.writerow({"image": img_path.name, **result})
            counts[result["view"]] += 1
            print(f"{img_path.name}: {result['view']} (confidence {result['confidence']:.2f})")
            annotated = annotate(image, result)
            cv2.imwrite(str(out_dir / img_path.name), annotated)
            if show and not show_image(f"{img_path.name}: {result['view']}", annotated):
                break

    if show:
        cv2.destroyAllWindows()
    summary = ", ".join(f"{v} {n}" for v, n in counts.items())
    print(f"Done: {summary} -> {out_dir}/views.csv")
    return counts


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", nargs="?", default=DATA_DIR / "input",
                   help="image file or directory of images, cropped to the B-mode view (default: data/classify_view/input/)")
    p.add_argument("output", nargs="?", default=DATA_DIR / "output", help="output directory (default: data/classify_view/output/)")
    p.add_argument("--show", action="store_true", help="display each annotated result in a window")
    a = p.parse_args()
    run(a.input, a.output, show=a.show)


if __name__ == "__main__":
    main()
