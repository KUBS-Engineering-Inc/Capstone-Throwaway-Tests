from dataclasses import dataclass

import cv2
import numpy as np

from config import (
    GREEN_HSV_LOWER,
    GREEN_HSV_UPPER,
    CURSOR_BEAM_REMOVAL_THICKNESS,
    CURSOR_MARKER_MIN_COMPONENT_AREA,
    HOUGH_MAXIMUM_LINE_GAP,
    HOUGH_RHO,
    HOUGH_THETA,
    HOUGH_THRESHOLD,
    MINIMUM_BEAM_LENGTH_PIXELS,
    MINIMUM_BEAM_LENGTH_RATIO,
    PREVIEW_BEAM_COLOR_BGR,
    PREVIEW_BEAM_THICKNESS,
    PREVIEW_ENDPOINT_COLOR_BGR,
    PREVIEW_ENDPOINT_RADIUS,
    PREVIEW_MASK_COLOR_BGR,
)


LineSegment = tuple[int, int, int, int]


@dataclass(frozen=True)
class DopplerCursorDetection:
    green_mask: np.ndarray
    line_segments: list[LineSegment]
    beam: LineSegment
    marker_center: tuple[int, int] | None


def create_green_pixel_mask(image: np.ndarray) -> np.ndarray:
    """Create a binary mask containing pixels within the configured green range."""
    print("[Cursor 1/4] Converting image from BGR to HSV.")
    print(
        f"[Cursor 1/4] Green HSV bounds: lower={GREEN_HSV_LOWER}, "
        f"upper={GREEN_HSV_UPPER}"
    )
    hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    green_mask = cv2.inRange(hsv_image, GREEN_HSV_LOWER, GREEN_HSV_UPPER)
    print(
        "[Cursor 1/4] "
        f"{cv2.countNonZero(green_mask)} pixels matched the green range."
    )
    return green_mask


def find_green_line_segments(green_mask: np.ndarray) -> list[LineSegment]:
    """Find line segments in the green mask using the probabilistic Hough transform."""
    minimum_length = max(
        MINIMUM_BEAM_LENGTH_PIXELS,
        int(green_mask.shape[0] * MINIMUM_BEAM_LENGTH_RATIO),
    )
    print("[Cursor 2/4] Searching the green mask for straight line segments.")
    print(
        f"[Cursor 2/4] Hough settings: vote threshold={HOUGH_THRESHOLD}, "
        f"minimum length={minimum_length}px, maximum gap={HOUGH_MAXIMUM_LINE_GAP}px."
    )
    segments = cv2.HoughLinesP(
        green_mask,
        rho=HOUGH_RHO,
        theta=HOUGH_THETA,
        threshold=HOUGH_THRESHOLD,
        minLineLength=minimum_length,
        maxLineGap=HOUGH_MAXIMUM_LINE_GAP,
    )
    if segments is None:
        print("[Cursor 2/4] No line segments were found.")
        raise ValueError("No line segments were detected in the green-pixel mask.")

    line_segments = [
        tuple(int(value) for value in segment)
        for segment in segments.reshape(-1, 4)
    ]
    print(f"[Cursor 2/4] Found {len(line_segments)} line segments:")
    for index, (x1, y1, x2, y2) in enumerate(line_segments, start=1):
        length = float(np.hypot(x2 - x1, y2 - y1))
        angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        print(
            f"[Cursor 2/4]   segment {index}: "
            f"({x1}, {y1}) -> ({x2}, {y2}), "
            f"length={length:.1f}px, angle={angle:.1f} degrees"
        )
    return line_segments


def find_longest_line_segment(segments: list[LineSegment]) -> LineSegment:
    """Return the longest segment, raising an error when the list is empty."""
    if not segments:
        raise ValueError("Cannot select a longest line from an empty segment list.")

    beam = max(
        segments,
        key=lambda segment: np.hypot(
            segment[2] - segment[0],
            segment[3] - segment[1],
        ),
    )
    length = float(np.hypot(beam[2] - beam[0], beam[3] - beam[1]))
    print(
        f"[Cursor 3/4] Selected longest segment as beam: "
        f"{beam}, length={length:.1f}px."
    )
    return beam


def find_cursor_marker_center(
    green_mask: np.ndarray,
    beam: LineSegment,
) -> tuple[int, int] | None:
    """Estimate the center of the short cursor marks after masking the long beam."""
    print(
        "[Cursor 4/4] Removing the selected beam from a copy of the mask "
        "to isolate shorter cursor marks."
    )
    marker_mask = green_mask.copy()
    x1, y1, x2, y2 = beam
    cv2.line(
        marker_mask,
        (x1, y1),
        (x2, y2),
        0,
        CURSOR_BEAM_REMOVAL_THICKNESS,
    )

    component_count, _, stats, centroids = cv2.connectedComponentsWithStats(
        marker_mask,
        connectivity=8,
    )
    marker_components = [
        index
        for index in range(1, component_count)
        if stats[index, cv2.CC_STAT_AREA] >= CURSOR_MARKER_MIN_COMPONENT_AREA
    ]
    print(
        f"[Cursor 4/4] Found {component_count - 1} connected green components "
        f"after beam removal; retaining components with area >= "
        f"{CURSOR_MARKER_MIN_COMPONENT_AREA}px."
    )
    if not marker_components:
        print("[Cursor 4/4] No marker components passed the area filter.")
        return None

    for index in marker_components:
        print(
            f"[Cursor 4/4]   component {index}: "
            f"area={stats[index, cv2.CC_STAT_AREA]}px, "
            f"centroid=({centroids[index, 0]:.1f}, {centroids[index, 1]:.1f})"
        )
    weights = np.array(
        [stats[index, cv2.CC_STAT_AREA] for index in marker_components],
        dtype=np.float64,
    )
    centers = centroids[marker_components]
    center_x, center_y = np.average(centers, axis=0, weights=weights)
    marker_center = round(float(center_x)), round(float(center_y))
    print(
        f"[Cursor 4/4] Area-weighted marker center: {marker_center}; "
        "this is an approximate search anchor."
    )
    return marker_center


def extract_doppler_cursor(image: np.ndarray) -> DopplerCursorDetection:
    """Detect green cursor pixels and choose the longest detected line as its beam."""
    print("\n=== Doppler cursor extraction ===")
    green_mask = create_green_pixel_mask(image)
    segments = find_green_line_segments(green_mask)
    beam = find_longest_line_segment(segments)
    marker_center = find_cursor_marker_center(green_mask, beam)
    return DopplerCursorDetection(green_mask, segments, beam, marker_center)


def create_cursor_preview(
    image: np.ndarray,
    green_mask: np.ndarray,
    beam: LineSegment,
) -> np.ndarray:
    """Overlay detected green pixels and the selected longest line on the source image."""
    preview = image.copy()
    preview[green_mask > 0] = PREVIEW_MASK_COLOR_BGR

    x1, y1, x2, y2 = beam
    cv2.line(
        preview,
        (x1, y1),
        (x2, y2),
        PREVIEW_BEAM_COLOR_BGR,
        PREVIEW_BEAM_THICKNESS,
    )
    cv2.circle(
        preview,
        (x1, y1),
        PREVIEW_ENDPOINT_RADIUS,
        PREVIEW_ENDPOINT_COLOR_BGR,
        -1,
    )
    cv2.circle(
        preview,
        (x2, y2),
        PREVIEW_ENDPOINT_RADIUS,
        PREVIEW_ENDPOINT_COLOR_BGR,
        -1,
    )
    return preview


def count_green_pixels(green_mask: np.ndarray) -> int:
    return int(cv2.countNonZero(green_mask))
