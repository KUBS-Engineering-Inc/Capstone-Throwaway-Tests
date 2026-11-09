"""Detect circular vessels (transverse view) in Doppler ultrasound images.

Usage:
    python modules/detect_circular_vessels/src/main.py [INPUT] [OUTPUT] [--method contour|hough] [--show]
                            [--min-circularity C] [--min-aspect A] [--min-contrast K]

INPUT is an image, or a directory of images, already cropped to the B-mode view
(default: data/detect_circular_vessels/input/).
OUTPUT is a directory (default: data/detect_circular_vessels/output/, created if needed). Every input image is
saved there with the overlay drawn on it (same filename), and all detections go
to OUTPUT/detections.csv (coordinates are in input-image pixels).
Overlay: yellow = traced lumen outline, red cross = centre, number = score.
--show also displays each overlay in a window (any key: next, q: close the window).

Method (classical OpenCV, no training):
  1. Inpaint thin overlays (green Doppler cursor, cyan colour box); treat
     colour-flow pixels (red/yellow/blue) as lumen.
  2. Sweep a darkness threshold. At each level, every dark connected region is a
     candidate lumen, so a lumen is caught at whichever level outlines it best.
  3. Keep candidates that are round (circularity, ellipse aspect, solidity), do
     not touch the image edge, and have a brighter wall ring than their interior.
  4. Merge overlapping candidates, keeping the highest-scoring one.

--method hough swaps step 2 for cv2.HoughCircles (HOUGH_GRADIENT_ALT) proposals,
checked with the same lumen tests. It tends to fit the outer bright wall rather
than the (often elliptical) lumen, so the contour method is the default.
"""
import argparse
import csv
import math
from pathlib import Path

import cv2
import numpy as np

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "detect_circular_vessels"  # modules/detect_circular_vessels/src/main.py -> repo root
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
WORK_SIZE = 300  # images are resized so their shorter side is this many px
THRESHOLDS = range(10, 95, 5)

# Settings used by run(). The command-line flags override them.
METHOD = "contour"       # "contour" (threshold sweep) or "hough" (cv2.HoughCircles)
MIN_CIRCULARITY = 0.75   # convex-hull circularity, 0..1
MIN_ASPECT = 0.4         # ellipse minor/major axis ratio
MIN_CONTRAST = 30        # wall minus lumen brightness, 0..255
SHOW = False             # also display each overlay in a window


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


def measure(contour, smooth, flow, clipped=None):
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

    r = math.sqrt(area / math.pi)
    k = max(3, int(0.4 * r)) | 1
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

    return dict(
        contour=contour,
        center=(float(cx), float(cy)),
        radius=r,
        area=float(area),
        major=float(major),
        minor=float(minor),
        aspect=float(minor / major) if major else 0.0,
        tilt=float(min(major_angle, 180 - major_angle)),  # major axis vs horizontal, 0..90
        circularity=float(4 * math.pi * hull_area / hull_perim ** 2) if hull_perim else 0.0,
        solidity=float(area / hull_area) if hull_area else 0.0,
        contrast=wall - interior,
        interior=interior,
        touches_edge=x <= 1 or y <= 1 or x + bw >= w - 1 or y + bh >= h - 1,
        flow_frac=float(flow[y0:y1, x0:x1][inside > 0].mean()) if flow is not None else 0.0,
        clipped_frac=float(clipped[y0:y1, x0:x1][inside > 0].mean()) if clipped is not None else 0.0,
    )


def dark_regions(gray, flow=None, clipped=None, min_radius_frac=0.03, max_radius_frac=0.35):
    """Every dark region found at any threshold level, measured. Yields dicts."""
    h, w = gray.shape
    smooth = cv2.GaussianBlur(cv2.medianBlur(gray, 5), (0, 0), 2)
    ell = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    min_area = math.pi * (min_radius_frac * min(h, w)) ** 2
    max_area = math.pi * (max_radius_frac * min(h, w)) ** 2
    for t in THRESHOLDS:
        mask = cv2.morphologyEx((smooth < t).astype(np.uint8), cv2.MORPH_OPEN, ell)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        for c in contours:
            if len(c) < 5 or not (min_area <= cv2.contourArea(c) <= max_area):
                continue
            reg = measure(c, smooth, flow, clipped)
            reg["threshold"] = t
            yield reg


def score(reg):
    """0..1 confidence that a region is a vessel cross-section."""
    shape = (reg["circularity"] + reg["aspect"] + reg["solidity"]) / 3
    contrast = min(1.0, reg["contrast"] / 80)
    return round(0.6 * shape + 0.4 * contrast, 3)


def is_circular(reg, min_circularity=MIN_CIRCULARITY, min_aspect=MIN_ASPECT, min_solidity=0.9,
                min_contrast=MIN_CONTRAST):
    return (not reg["touches_edge"]
            and reg["clipped_frac"] <= 0.5  # flow blob cut off by the colour box
            and reg["circularity"] >= min_circularity
            and reg["aspect"] >= min_aspect
            and reg["solidity"] >= min_solidity
            and reg["contrast"] >= min_contrast
            and reg["interior"] < 0.6 * (reg["interior"] + reg["contrast"]))  # lumen < 60% of wall


def suppress(regs, shape, overlap=0.3):
    """Non-maximum suppression: drop regions that overlap a higher-scoring one."""
    kept = []
    for reg in sorted(regs, key=lambda r: r["score"], reverse=True):
        reg["mask"] = np.zeros(shape, np.uint8)
        cv2.drawContours(reg["mask"], [reg["contour"]], -1, 1, cv2.FILLED)
        if all(np.logical_and(reg["mask"], k["mask"]).sum() < overlap * min(reg["area"], k["area"])
               for k in kept):
            kept.append(reg)
    return kept


def hough_regions(gray, flow=None, clipped=None, min_radius_frac=0.03, max_radius_frac=0.35, param2=0.7):
    """Circles from cv2.HoughCircles (HOUGH_GRADIENT_ALT), measured like dark regions.

    Ultrasound shows the top and bottom vessel walls brightly but the side walls
    weakly, so circles often lock onto the outer wall. Each circle is therefore
    measured on its inner 80% (lumen) against a ring just outside it (wall).
    """
    h, w = gray.shape
    smooth = cv2.GaussianBlur(cv2.medianBlur(gray, 5), (0, 0), 2)
    m = min(h, w)
    circles = cv2.HoughCircles(smooth, cv2.HOUGH_GRADIENT_ALT, dp=1.5, minDist=int(0.08 * m),
                               param1=150, param2=param2,
                               minRadius=int(min_radius_frac * m), maxRadius=int(max_radius_frac * m))
    if circles is None:
        return
    for x, y, r in circles[0][:, :3]:
        disc = np.zeros((h, w), np.uint8)
        cv2.circle(disc, (int(x), int(y)), max(2, int(0.8 * r)), 1, cv2.FILLED)
        contours, _ = cv2.findContours(disc, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if contours and len(contours[0]) >= 5:
            reg = measure(contours[0], smooth, flow, clipped)
            reg["threshold"] = None
            yield reg


def to_work_size(bgr):
    """Resize so the shorter side is WORK_SIZE px; return (image, scale)."""
    s = WORK_SIZE / min(bgr.shape[:2])
    return cv2.resize(bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR), s


def detect_contour(image, **thresholds):
    """Detect circular vessels with the threshold sweep (dark_regions).
    Returned coordinates are in input-image pixels."""
    return _detect(image, dark_regions, **thresholds)


def detect_hough(image, **thresholds):
    """Detect circular vessels with cv2.HoughCircles (hough_regions).
    Returned coordinates are in input-image pixels."""
    return _detect(image, hough_regions, **thresholds)


def _detect(image, find_regions, **thresholds):
    """Shared by both methods: clean the view, find candidate regions with
    `find_regions`, keep the circular ones, merge overlaps, scale back."""
    work, s = to_work_size(image)
    gray, flow, clipped = clean_view(work)
    regions = find_regions(gray, flow, clipped)
    cands = []
    for reg in regions:
        if is_circular(reg, **thresholds):
            reg["score"] = score(reg)
            cands.append(reg)
    dets = []
    for reg in suppress(cands, gray.shape):
        cx, cy = reg["center"]
        dets.append(dict(
            cx=round(cx / s, 1), cy=round(cy / s, 1), radius=round(reg["radius"] / s, 1),
            major=round(reg["major"] / s, 1), minor=round(reg["minor"] / s, 1),
            circularity=round(reg["circularity"], 3), aspect=round(reg["aspect"], 3),
            contrast=round(reg["contrast"], 1), color_flow=reg["flow_frac"] > 0.2, score=reg["score"],
            contour=np.round(reg["contour"] / s).astype(np.int32),
        ))
    return dets


def annotate(image, dets):
    out = image.copy()
    for d in dets:
        cv2.drawContours(out, [d["contour"]], -1, (0, 255, 255), 2)
        c = (int(d["cx"]), int(d["cy"]))
        cv2.drawMarker(out, c, (0, 0, 255), cv2.MARKER_CROSS, 10, 2)
        cv2.putText(out, f"{d['score']:.2f}", (c[0] + 8, c[1] - 8), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (0, 255, 255), 1, cv2.LINE_AA)
    return out


def show_image(title, image):
    """Display an image; returns False if the user pressed q/Esc to stop."""
    cv2.imshow("result", image)
    cv2.setWindowTitle("result", f"{title}  (any key: next, q: close)")
    return cv2.waitKey(0) & 0xFF not in (ord("q"), 27)


def list_images(path):
    path = Path(path)
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    raise FileNotFoundError(f"Input not found: {path}")


def run(input, output):
    """Detect circular vessels in every image under `input`; write overlays and
    detections.csv to `output`, using the settings at the top of this file.
    Returns the number of images with a detection."""
    images = list_images(input)
    thresholds = dict(min_circularity=MIN_CIRCULARITY, min_aspect=MIN_ASPECT, min_contrast=MIN_CONTRAST)
    detect = detect_hough if METHOD == "hough" else detect_contour

    # 1. Detect in every image.
    detections = {}  # image path -> list of detections
    for img_path in images:
        image = cv2.imread(str(img_path))
        if image is None:
            print(f"Skipping unreadable image: {img_path}")
            continue
        detections[img_path] = detect(image, **thresholds)
        print(f"{img_path.name}: {len(detections[img_path])} circular vessel(s)")

    # 2. Draw the detections on each image.
    overlays = {}  # image file name -> annotated image
    showing = SHOW
    for img_path, dets in detections.items():
        overlays[img_path.name] = annotate(cv2.imread(str(img_path)), dets)
        if showing:  # q/Esc closes the viewer; the remaining images are still drawn
            showing = show_image(f"{img_path.name}: {len(dets)} vessel(s)", overlays[img_path.name])
    if SHOW:
        cv2.destroyAllWindows()

    # 3. Write the results.
    rows = [{"image": img_path.name, **d} for img_path, dets in detections.items() for d in dets]
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, overlay in overlays.items():
        cv2.imwrite(str(out_dir / name), overlay)
    fields = ["image", "cx", "cy", "radius", "major", "minor", "circularity", "aspect", "contrast", "color_flow", "score"]
    with open(out_dir / "detections.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    hits = len({r["image"] for r in rows})
    print(f"Done: {hits} of {len(images)} image(s) had circular vessels -> {out_dir}/")
    return hits


def main():
    global METHOD, MIN_CIRCULARITY, MIN_ASPECT, MIN_CONTRAST, SHOW
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", nargs="?", default=DATA_DIR / "input",
                   help="image file or directory of images, cropped to the B-mode view (default: data/detect_circular_vessels/input/)")
    p.add_argument("output", nargs="?", default=DATA_DIR / "output", help="output directory (default: data/detect_circular_vessels/output/)")
    p.add_argument("--method", choices=["contour", "hough"], default=METHOD,
                   help=f"contour: threshold-sweep segmentation; hough: cv2.HoughCircles (default: {METHOD})")
    p.add_argument("--min-circularity", type=float, default=MIN_CIRCULARITY,
                   help=f"convex-hull circularity, 0..1 (default: {MIN_CIRCULARITY})")
    p.add_argument("--min-aspect", type=float, default=MIN_ASPECT,
                   help=f"ellipse minor/major axis ratio (default: {MIN_ASPECT})")
    p.add_argument("--min-contrast", type=float, default=MIN_CONTRAST,
                   help=f"wall minus lumen brightness, 0..255 (default: {MIN_CONTRAST})")
    p.add_argument("--show", action="store_true", help="display each annotated result in a window")
    a = p.parse_args()
    METHOD, MIN_CIRCULARITY, MIN_ASPECT, MIN_CONTRAST, SHOW = (
        a.method, a.min_circularity, a.min_aspect, a.min_contrast, a.show)
    run(a.input, a.output)


if __name__ == "__main__":
    main()
