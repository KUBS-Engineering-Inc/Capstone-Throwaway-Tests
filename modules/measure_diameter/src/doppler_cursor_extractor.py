from dataclasses import dataclass

import cv2
import numpy as np

from config import (
    GREEN_HSV_LOWER,
    GREEN_HSV_UPPER,
    CURSOR_BEAM_REMOVAL_THICKNESS,
    CURSOR_LINE_FIT_DISTANCE_PIXELS,
    CURSOR_LINE_MAX_ANGLE_DIFF_DEGREES,
    CURSOR_LINE_MIN_ANGLE_DIFF_DEGREES,
    CURSOR_LINE_PAIR_MAX_ANGLE_DIFF_DEGREES,
    CURSOR_LINE_PAIR_MAX_OFFSET_PIXELS,
    HOUGH_MAXIMUM_LINE_GAP,
    HOUGH_RHO,
    HOUGH_THETA,
    HOUGH_THRESHOLD,
    INSONATION_HOUGH_THRESHOLD,
    INSONATION_MAX_LINE_GAP,
    INSONATION_MIN_LINE_LENGTH,
    MINIMUM_BEAM_LENGTH_PIXELS,
    MINIMUM_BEAM_LENGTH_RATIO,
    PREVIEW_BEAM_COLOR_BGR,
    PREVIEW_BEAM_THICKNESS,
    PREVIEW_CENTER_COLOR_BGR,
    PREVIEW_ENDPOINT_COLOR_BGR,
    PREVIEW_ENDPOINT_RADIUS,
    PREVIEW_INSONATION_COLOR_BGR,
    PREVIEW_MASK_COLOR_BGR,
)


LineSegment = tuple[int, int, int, int]
FittedLine = tuple[float, float, float, float]


@dataclass(frozen=True)
class DopplerCursorDetection:
    green_mask: np.ndarray
    line_segments: list[LineSegment]
    beam: LineSegment
    insonation_line: FittedLine | None
    cursor_center: tuple[int, int] | None


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


def _angle_difference_degrees(first: float, second: float) -> float:
    return abs((first - second + 90) % 180 - 90)


def _line_fit(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    fitted = cv2.fitLine(
        points.astype(np.float32).reshape(-1, 1, 2),
        cv2.DIST_L2,
        0,
        0.01,
        0.01,
    ).flatten()
    direction = fitted[:2].astype(np.float64)
    origin = fitted[2:].astype(np.float64)
    return direction, origin


def _cross_2d(first: np.ndarray, second: np.ndarray) -> float:
    return float(first[0] * second[1] - first[1] * second[0])


def find_cursor_intersection(
    green_mask: np.ndarray,
    beam: LineSegment,
) -> tuple[FittedLine | None, tuple[int, int] | None]:
    """Fit the insonation stroke and intersect it with the Doppler beam."""
    print(
        "[Cursor 4/4] Masking the selected beam in a copy of the green mask "
        "so it cannot interfere with fitting the insonation stroke."
    )
    other_strokes = green_mask.copy()
    x1, y1, x2, y2 = beam
    cv2.line(
        other_strokes,
        (x1, y1),
        (x2, y2),
        0,
        CURSOR_BEAM_REMOVAL_THICKNESS,
    )

    print(
        "[Cursor 4/4] Detecting the remaining straight strokes with relaxed "
        f"Hough settings: vote threshold={INSONATION_HOUGH_THRESHOLD}, "
        f"minimum length={INSONATION_MIN_LINE_LENGTH}px, "
        f"maximum gap={INSONATION_MAX_LINE_GAP}px."
    )
    detected = cv2.HoughLinesP(
        other_strokes,
        rho=HOUGH_RHO,
        theta=HOUGH_THETA,
        threshold=INSONATION_HOUGH_THRESHOLD,
        minLineLength=INSONATION_MIN_LINE_LENGTH,
        maxLineGap=INSONATION_MAX_LINE_GAP,
    )
    if detected is None:
        print("[Cursor 4/4] No candidate strokes were detected after beam masking.")
        return None, None

    beam_start = np.array((x1, y1), dtype=np.float64)
    beam_direction = np.array((x2 - x1, y2 - y1), dtype=np.float64)
    beam_length = float(np.linalg.norm(beam_direction))
    beam_direction /= beam_length
    beam_angle = float(np.degrees(np.arctan2(beam_direction[1], beam_direction[0])))
    candidate_segments: list[tuple[LineSegment, float, float]] = []
    for raw_segment in detected.reshape(-1, 4):
        segment = tuple(int(value) for value in raw_segment)
        sx1, sy1, sx2, sy2 = segment
        direction = np.array((sx2 - sx1, sy2 - sy1), dtype=np.float64)
        length = float(np.linalg.norm(direction))
        angle = float(np.degrees(np.arctan2(direction[1], direction[0])))
        difference = _angle_difference_degrees(angle, beam_angle)
        midpoint = np.array(((sx1 + sx2) / 2, (sy1 + sy2) / 2))
        side = _cross_2d(beam_direction, midpoint - beam_start)
        print(
            f"[Cursor 4/4]   candidate {segment}: length={length:.1f}px, "
            f"angle={angle:.1f} degrees, angle to beam={difference:.1f} "
            f"degrees, beam-side={'left' if side < 0 else 'right'}."
        )
        if (
            difference < CURSOR_LINE_MIN_ANGLE_DIFF_DEGREES
            or difference > CURSOR_LINE_MAX_ANGLE_DIFF_DEGREES
        ):
            continue
        candidate_segments.append((segment, length, side))

    best_pair: tuple[LineSegment, LineSegment] | None = None
    best_direction: np.ndarray | None = None
    best_origin: np.ndarray | None = None
    best_score = -1.0
    for index, (first, first_length, first_side) in enumerate(candidate_segments):
        for second, second_length, second_side in candidate_segments[index + 1 :]:
            if first_side * second_side >= 0:
                continue
            first_angle = float(np.degrees(np.arctan2(first[3] - first[1], first[2] - first[0])))
            second_angle = float(np.degrees(np.arctan2(second[3] - second[1], second[2] - second[0])))
            if _angle_difference_degrees(first_angle, second_angle) > CURSOR_LINE_PAIR_MAX_ANGLE_DIFF_DEGREES:
                continue

            endpoints = np.array(
                ((first[0], first[1]), (first[2], first[3]),
                 (second[0], second[1]), (second[2], second[3])),
                dtype=np.float64,
            )
            fit_direction, fit_origin = _line_fit(endpoints)
            offsets = np.abs(
                (endpoints[:, 0] - fit_origin[0]) * fit_direction[1]
                - (endpoints[:, 1] - fit_origin[1]) * fit_direction[0]
            )
            max_offset = float(np.max(offsets))
            if max_offset > CURSOR_LINE_PAIR_MAX_OFFSET_PIXELS:
                continue
            score = (first_length + second_length) / (1 + max_offset)
            if score > best_score:
                best_pair = first, second
                best_direction = fit_direction
                best_origin = fit_origin
                best_score = score

    if best_pair is None or best_direction is None or best_origin is None:
        print(
            "[Cursor 4/4] Could not find two aligned insonation-stroke portions "
            "on opposite sides of the beam."
        )
        return None, None

    print(
        f"[Cursor 4/4] Paired stroke portions {best_pair[0]} and {best_pair[1]}; "
        f"combined line-fit score={best_score:.2f}."
    )
    coordinates_y, coordinates_x = np.where(other_strokes > 0)
    pixels = np.column_stack((coordinates_x, coordinates_y)).astype(np.float64)
    relative_pixels = pixels - best_origin
    distances = np.abs(
        relative_pixels[:, 0] * best_direction[1]
        - relative_pixels[:, 1] * best_direction[0]
    )
    projections = relative_pixels @ best_direction
    endpoints = np.array(
        (*best_pair[0][:2], *best_pair[0][2:], *best_pair[1][:2], *best_pair[1][2:]),
        dtype=np.float64,
    ).reshape(-1, 2)
    endpoint_projections = (endpoints - best_origin) @ best_direction
    in_span = (
        (projections >= endpoint_projections.min() - 3)
        & (projections <= endpoint_projections.max() + 3)
    )
    fit_pixels = pixels[(distances <= CURSOR_LINE_FIT_DISTANCE_PIXELS) & in_span]
    if len(fit_pixels) < 2:
        raise ValueError("Too few green pixels remained to fit the insonation line.")
    insonation_direction, insonation_origin = _line_fit(fit_pixels)
    print(
        f"[Cursor 4/4] Refitted insonation line using {len(fit_pixels)} green "
        f"pixels; direction=({insonation_direction[0]:.3f}, "
        f"{insonation_direction[1]:.3f})."
    )

    denominator = _cross_2d(insonation_direction, beam_direction)
    if abs(denominator) < 1e-6:
        print("[Cursor 4/4] Insonation line is parallel to the beam; no crossing.")
        return None, None
    distance_to_intersection = _cross_2d(
        beam_start - insonation_origin,
        beam_direction,
    ) / denominator
    intersection = insonation_origin + distance_to_intersection * insonation_direction
    beam_position = float((intersection - beam_start) @ beam_direction)
    if beam_position < -2 or beam_position > beam_length + 2:
        print(
            f"[Cursor 4/4] Fitted-line crossing is outside the detected beam "
            f"segment: distance={beam_position:.1f}px, beam length={beam_length:.1f}px."
        )
        return None, None

    fitted_projections = (fit_pixels - insonation_origin) @ insonation_direction
    fitted_start = insonation_origin + fitted_projections.min() * insonation_direction
    fitted_end = insonation_origin + fitted_projections.max() * insonation_direction
    insonation_line = (
        float(fitted_start[0]),
        float(fitted_start[1]),
        float(fitted_end[0]),
        float(fitted_end[1]),
    )
    cursor_center = round(float(intersection[0])), round(float(intersection[1]))
    print(
        f"[Cursor 4/4] Beam/insonation intersection: "
        f"({intersection[0]:.2f}, {intersection[1]:.2f}) -> "
        f"pixel {cursor_center}; used as the lumen-search anchor."
    )
    return insonation_line, cursor_center


def extract_doppler_cursor(image: np.ndarray) -> DopplerCursorDetection:
    """Detect green cursor pixels and choose the longest detected line as its beam."""
    print("\n=== Doppler cursor extraction ===")
    green_mask = create_green_pixel_mask(image)
    segments = find_green_line_segments(green_mask)
    beam = find_longest_line_segment(segments)
    insonation_line, cursor_center = find_cursor_intersection(green_mask, beam)
    return DopplerCursorDetection(
        green_mask,
        segments,
        beam,
        insonation_line,
        cursor_center,
    )


def create_cursor_preview(
    image: np.ndarray,
    green_mask: np.ndarray,
    beam: LineSegment,
    insonation_line: FittedLine | None,
    cursor_center: tuple[int, int] | None,
) -> np.ndarray:
    """Overlay the fitted beam, insonation stroke, and their intersection."""
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
    if insonation_line is not None:
        ix1, iy1, ix2, iy2 = insonation_line
        cv2.line(
            preview,
            (round(ix1), round(iy1)),
            (round(ix2), round(iy2)),
            PREVIEW_INSONATION_COLOR_BGR,
            PREVIEW_BEAM_THICKNESS,
        )
    if cursor_center is not None:
        cv2.drawMarker(
            preview,
            cursor_center,
            PREVIEW_CENTER_COLOR_BGR,
            cv2.MARKER_CROSS,
            11,
            2,
        )
    return preview


def count_green_pixels(green_mask: np.ndarray) -> int:
    return int(cv2.countNonZero(green_mask))
