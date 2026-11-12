from dataclasses import dataclass
import math

import cv2
import numpy as np

from config import (
    LUMEN_CROSS_SECTION_COLOR_BGR,
    LUMEN_CONTOUR_COLOR_BGR,
    LUMEN_CENTER_COLOR_BGR,
    LUMEN_GAUSSIAN_BLUR_SIGMA,
    LUMEN_MASK_OVERLAY_COLOR_BGR,
    LUMEN_MAX_VERTICAL_FRACTION,
    LUMEN_MEDIAN_BLUR_SIZE,
    LUMEN_MIN_COMPONENT_AREA,
    LUMEN_MORPHOLOGY_KERNEL_SIZE,
    LUMEN_RING_KERNEL_SIZE,
    LUMEN_SEARCH_HALF_HEIGHT,
    LUMEN_SEARCH_HALF_WIDTH,
    LUMEN_SWEEP_COLUMNS,
    LUMEN_THRESHOLD_START,
    LUMEN_THRESHOLD_STEP,
    LUMEN_THRESHOLD_STOP,
    LUMEN_PREVIEW_HEADER_HEIGHT,
)


Point = tuple[int, int]
SearchRegion = tuple[int, int, int, int]


@dataclass(frozen=True)
class LumenCandidate:
    threshold: int
    mask: np.ndarray
    contour: np.ndarray
    search_region: SearchRegion
    area_pixels: int
    vertical_extent_pixels: int
    axis_angle_degrees: float
    lumen_mean_intensity: float
    wall_ring_mean_intensity: float
    wall_contrast: float
    cross_section_width_pixels: float
    cross_section: tuple[Point, Point]


def create_lumen_search_region(
    image_shape: tuple[int, ...],
    center: Point,
) -> SearchRegion:
    """Create an image-clipped region around the Doppler cursor's marker center."""
    image_height, image_width = image_shape[:2]
    center_x, center_y = center
    left = max(0, center_x - LUMEN_SEARCH_HALF_WIDTH)
    top = max(0, center_y - LUMEN_SEARCH_HALF_HEIGHT)
    right = min(image_width, center_x + LUMEN_SEARCH_HALF_WIDTH + 1)
    bottom = min(image_height, center_y + LUMEN_SEARCH_HALF_HEIGHT + 1)
    return left, top, right - left, bottom - top


def clean_lumen_view(image: np.ndarray, cursor_mask: np.ndarray) -> np.ndarray:
    """Remove cursor-color pixels and smooth speckle before threshold segmentation."""
    print("[Lumen 1/4] Converting the input image to grayscale.")
    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    print(
        "[Lumen 1/4] "
        f"Grayscale brightness range: {int(grayscale.min())}..{int(grayscale.max())}; "
        f"mean={float(grayscale.mean()):.1f}."
    )
    expanded_cursor_mask = cv2.dilate(
        cursor_mask,
        np.ones((3, 3), dtype=np.uint8),
    )
    print(
        "[Lumen 1/4] Inpainting "
        f"{cv2.countNonZero(expanded_cursor_mask)} cursor/near-cursor pixels "
        "using nearby grayscale values."
    )
    inpainted = cv2.inpaint(
        grayscale,
        expanded_cursor_mask,
        inpaintRadius=3,
        flags=cv2.INPAINT_TELEA,
    )
    median_filtered = cv2.medianBlur(inpainted, LUMEN_MEDIAN_BLUR_SIZE)
    print(
        "[Lumen 1/4] Applying median blur "
        f"(kernel={LUMEN_MEDIAN_BLUR_SIZE}) and Gaussian blur "
        f"(sigma={LUMEN_GAUSSIAN_BLUR_SIGMA}) to reduce small speckle."
    )
    cleaned = cv2.GaussianBlur(
        median_filtered,
        (0, 0),
        LUMEN_GAUSSIAN_BLUR_SIGMA,
    )
    print(
        "[Lumen 1/4] Cleaned brightness range: "
        f"{int(cleaned.min())}..{int(cleaned.max())}; "
        f"mean={float(cleaned.mean()):.1f}."
    )
    return cleaned


def extract_lumen_candidates(
    image: np.ndarray,
    cursor_mask: np.ndarray,
    center: Point,
) -> list[LumenCandidate]:
    """Sweep darkness thresholds and retain the dark component containing the cursor point."""
    print("\n=== Cursor-anchored lumen candidate search ===")
    clean_image = clean_lumen_view(image, cursor_mask)
    left, top, width, height = create_lumen_search_region(image.shape, center)
    search_region = (left, top, width, height)
    region = clean_image[top : top + height, left : left + width]
    anchor_x = center[0] - left
    anchor_y = center[1] - top
    print(
        "[Lumen 2/4] Search region in full-image coordinates: "
        f"x={left}..{left + width - 1}, y={top}..{top + height - 1} "
        f"({width}x{height}px)."
    )
    print(
        f"[Lumen 2/4] Anchor in image coordinates={center}; "
        f"within-region coordinates=({anchor_x}, {anchor_y}); "
        f"cleaned brightness at anchor={int(region[anchor_y, anchor_x])}."
    )
    print(
        "[Lumen 2/4] Threshold sweep: "
        f"{LUMEN_THRESHOLD_START} to {LUMEN_THRESHOLD_STOP - LUMEN_THRESHOLD_STEP} "
        f"in steps of {LUMEN_THRESHOLD_STEP}; threshold means pixels darker "
        "than that value are included."
    )
    print(
        "[Lumen 2/4] Each threshold mask is morphologically opened with an "
        f"elliptical {LUMEN_MORPHOLOGY_KERNEL_SIZE}x"
        f"{LUMEN_MORPHOLOGY_KERNEL_SIZE} kernel."
    )
    morphology_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (LUMEN_MORPHOLOGY_KERNEL_SIZE, LUMEN_MORPHOLOGY_KERNEL_SIZE),
    )

    candidates: list[LumenCandidate] = []
    thresholds = range(
        LUMEN_THRESHOLD_START,
        LUMEN_THRESHOLD_STOP,
        LUMEN_THRESHOLD_STEP,
    )
    for sweep_index, threshold in enumerate(thresholds, start=1):
        print(
            f"[Lumen 3/4] Threshold {sweep_index}: t={threshold}; "
            f"building the dark-pixel mask."
        )
        dark_mask = (region < threshold).astype(np.uint8)
        dark_pixel_count = cv2.countNonZero(dark_mask)
        opened_mask = cv2.morphologyEx(
            dark_mask,
            cv2.MORPH_OPEN,
            morphology_kernel,
        )
        component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
            opened_mask,
            connectivity=8,
        )
        component_label = int(labels[anchor_y, anchor_x])
        print(
            f"[Lumen 3/4]   dark pixels before opening={dark_pixel_count}; "
            f"after opening={cv2.countNonZero(opened_mask)}; "
            f"foreground components={component_count - 1}; "
            f"anchor label={component_label}."
        )
        if component_label == 0:
            print("[Lumen 3/4]   rejected: anchor is not in a dark component.")
            continue

        component_stats = stats[component_label]
        area = int(component_stats[cv2.CC_STAT_AREA])
        component_height = int(component_stats[cv2.CC_STAT_HEIGHT])
        component_left = int(component_stats[cv2.CC_STAT_LEFT]) + left
        component_top = int(component_stats[cv2.CC_STAT_TOP]) + top
        component_width = int(component_stats[cv2.CC_STAT_WIDTH])
        print(
            f"[Lumen 3/4]   anchor component: area={area}px; "
            f"bounding box=({component_left}, {component_top}, "
            f"{component_width}x{component_height}px)."
        )
        if area < LUMEN_MIN_COMPONENT_AREA:
            print(
                f"[Lumen 3/4]   rejected: area {area}px is below the "
                f"{LUMEN_MIN_COMPONENT_AREA}px minimum."
            )
            continue
        if component_height > height * LUMEN_MAX_VERTICAL_FRACTION:
            print(
                f"[Lumen 3/4]   rejected: component height {component_height}px "
                f"exceeds {LUMEN_MAX_VERTICAL_FRACTION:.0%} of the "
                f"{height}px search region."
            )
            continue

        component_mask = (labels == component_label).astype(np.uint8)
        contours, _ = cv2.findContours(
            component_mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_NONE,
        )
        if not contours:
            print("[Lumen 3/4]   rejected: no contour could be formed.")
            continue

        contour = max(contours, key=cv2.contourArea)
        contour = contour + np.asarray((left, top), dtype=np.int32)
        component_points = np.column_stack(np.where(component_mask > 0))[:, ::-1]
        axis, axis_angle_degrees = _estimate_long_axis(component_points)
        normal = np.asarray((-axis[1], axis[0]), dtype=np.float64)
        diameter_pixels, cross_section = _measure_cross_section(
            component_mask,
            (anchor_x, anchor_y),
            (left, top),
            normal,
            max(width, height),
        )
        if diameter_pixels is None or cross_section is None:
            print(
                "[Lumen 3/4]   rejected: could not measure a continuous "
                "cross-section through the anchor."
            )
            continue

        ring_kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (LUMEN_RING_KERNEL_SIZE, LUMEN_RING_KERNEL_SIZE),
        )
        dilated = cv2.dilate(component_mask, ring_kernel)
        ring_mask = (dilated > 0) & (component_mask == 0)
        lumen_pixels = region[component_mask > 0]
        ring_pixels = region[ring_mask]
        lumen_mean = float(np.mean(lumen_pixels))
        ring_mean = float(np.mean(ring_pixels)) if ring_pixels.size else lumen_mean

        global_cross_section = (
            (cross_section[0][0] + left, cross_section[0][1] + top),
            (cross_section[1][0] + left, cross_section[1][1] + top),
        )
        print(
            f"[Lumen 3/4]   candidate accepted: cross-section width="
            f"{diameter_pixels:.1f}px; endpoints={global_cross_section}; "
            f"estimated long-axis angle={axis_angle_degrees:.1f} degrees."
        )
        print(
            f"[Lumen 3/4]   grayscale means: lumen={lumen_mean:.1f}, "
            f"surrounding ring={ring_mean:.1f}, "
            f"ring-minus-lumen contrast={ring_mean - lumen_mean:.1f}."
        )
        candidates.append(
            LumenCandidate(
                threshold=threshold,
                mask=component_mask,
                contour=contour,
                search_region=search_region,
                area_pixels=area,
                vertical_extent_pixels=component_height,
                axis_angle_degrees=axis_angle_degrees,
                lumen_mean_intensity=lumen_mean,
                wall_ring_mean_intensity=ring_mean,
                wall_contrast=ring_mean - lumen_mean,
                cross_section_width_pixels=diameter_pixels,
                cross_section=global_cross_section,
            )
        )

    print(
        f"[Lumen 3/4] Threshold sweep complete: "
        f"{len(candidates)} candidate(s) accepted."
    )
    return candidates


def create_lumen_threshold_sweep_preview(
    image: np.ndarray,
    center: Point,
    candidates: list[LumenCandidate],
) -> np.ndarray:
    """Create a contact sheet showing the anchor-containing region at each threshold."""
    if not candidates:
        raise ValueError("No dark lumen candidate containing the cursor point was found.")

    print(
        f"[Lumen 4/4] Building threshold contact sheet from "
        f"{len(candidates)} candidate masks."
    )
    left, top, width, height = candidates[0].search_region
    image_region = image[top : top + height, left : left + width]
    tiles: list[np.ndarray] = []
    for candidate in candidates:
        print(
            f"[Lumen 4/4]   drawing threshold={candidate.threshold}, "
            f"mask pixels={candidate.area_pixels}, "
            f"cross-section width={candidate.cross_section_width_pixels:.1f}px."
        )
        tile = image_region.copy()
        tint = np.full_like(tile, LUMEN_MASK_OVERLAY_COLOR_BGR)
        selected = candidate.mask > 0
        tile[selected] = cv2.addWeighted(
            tile[selected],
            0.45,
            tint[selected],
            0.55,
            0,
        )
        local_contour = candidate.contour - np.asarray((left, top), dtype=np.int32)
        cv2.drawContours(tile, [local_contour], -1, LUMEN_CONTOUR_COLOR_BGR, 1)
        local_center = (center[0] - left, center[1] - top)
        cv2.circle(tile, local_center, 3, LUMEN_CENTER_COLOR_BGR, -1)
        local_cross_section = tuple(
            (point[0] - left, point[1] - top)
            for point in candidate.cross_section
        )
        cv2.line(
            tile,
            local_cross_section[0],
            local_cross_section[1],
            LUMEN_CROSS_SECTION_COLOR_BGR,
            1,
        )
        tiles.append(_add_candidate_label(tile, candidate))

    columns = LUMEN_SWEEP_COLUMNS
    rows = math.ceil(len(tiles) / columns)
    tile_height = tiles[0].shape[0]
    tile_width = tiles[0].shape[1]
    montage = np.zeros(
        (rows * tile_height, columns * tile_width, 3),
        dtype=np.uint8,
    )
    for index, tile in enumerate(tiles):
        row, column = divmod(index, columns)
        y = row * tile_height
        x = column * tile_width
        montage[y : y + tile_height, x : x + tile_width] = tile
    print(
        f"[Lumen 4/4] Contact sheet dimensions: "
        f"{montage.shape[1]}x{montage.shape[0]} pixels "
        f"({columns} columns, {rows} rows)."
    )
    return montage


def _estimate_long_axis(points: np.ndarray) -> tuple[np.ndarray, float]:
    centered = points.astype(np.float64) - np.mean(points, axis=0)
    covariance = np.cov(centered, rowvar=False)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    axis = eigenvectors[:, int(np.argmax(eigenvalues))]
    angle = math.degrees(math.atan2(float(axis[1]), float(axis[0])))
    if angle > 90:
        angle -= 180
    elif angle < -90:
        angle += 180
    print(
        "[Lumen 3/4]   principal-axis fit: "
        f"component pixels={len(points)}, centroid="
        f"({np.mean(points[:, 0]):.1f}, {np.mean(points[:, 1]):.1f}), "
        f"spread eigenvalues=({eigenvalues[0]:.1f}, {eigenvalues[1]:.1f}), "
        f"major-axis direction=({axis[0]:.3f}, {axis[1]:.3f})."
    )
    return axis, angle


def _measure_cross_section(
    mask: np.ndarray,
    anchor: Point,
    offset: Point,
    normal: np.ndarray,
    maximum_distance: int,
) -> tuple[float | None, tuple[Point, Point] | None]:
    anchor_x, anchor_y = anchor
    if mask[anchor_y, anchor_x] == 0:
        print(
            "[Lumen 3/4]   cross-section measurement stopped: "
            "anchor is outside this candidate mask."
        )
        return None, None

    print(
        f"[Lumen 3/4]   sampling candidate mask along the estimated "
        f"perpendicular direction (normal=({normal[0]:.3f}, {normal[1]:.3f}))."
    )
    distances = np.arange(-maximum_distance, maximum_distance + 1)
    xs = np.rint(anchor_x + distances * normal[0]).astype(int)
    ys = np.rint(anchor_y + distances * normal[1]).astype(int)
    in_bounds = (
        (xs >= 0)
        & (xs < mask.shape[1])
        & (ys >= 0)
        & (ys < mask.shape[0])
    )
    inside = np.zeros(distances.shape, dtype=bool)
    inside[in_bounds] = mask[ys[in_bounds], xs[in_bounds]] > 0
    anchor_index = maximum_distance
    if not inside[anchor_index]:
        print(
            "[Lumen 3/4]   cross-section measurement stopped: "
            "sampled center is not inside the component."
        )
        return None, None

    start = anchor_index
    while start > 0 and inside[start - 1]:
        start -= 1
    end = anchor_index
    while end + 1 < len(inside) and inside[end + 1]:
        end += 1

    point_a = (
        int(xs[start]),
        int(ys[start]),
    )
    point_b = (
        int(xs[end]),
        int(ys[end]),
    )
    sample_count = float(end - start + 1)
    print(
        f"[Lumen 3/4]   contiguous inside-mask sample range: "
        f"{start - anchor_index}..{end - anchor_index}; "
        f"count={sample_count:.1f}px; local endpoints={point_a} and {point_b}."
    )
    return sample_count, (point_a, point_b)


def _add_candidate_label(tile: np.ndarray, candidate: LumenCandidate) -> np.ndarray:
    header = np.zeros(
        (LUMEN_PREVIEW_HEADER_HEIGHT, tile.shape[1], 3),
        dtype=np.uint8,
    )
    label = (
        f"t={candidate.threshold} width={candidate.cross_section_width_pixels:.0f}px "
        f"contrast={candidate.wall_contrast:.0f}"
    )
    cv2.putText(
        header,
        label,
        (4, LUMEN_PREVIEW_HEADER_HEIGHT - 7),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return np.vstack((header, tile))
