import cv2

from config import (
    B_MODE_FULL_BOTTOM,
    B_MODE_SEARCH_LEFT,
    B_MODE_SEARCH_RIGHT,
    B_MODE_SEARCH_TOP,
    B_MODE_SPLIT_BOTTOM,
    CONTOUR_THRESHOLD,
    SPECTRAL_WINDOW,
)
from image_utils import crop


def get_b_mode_search_bounds(mode):
    """Return full-frame search bounds for the B-mode panel in this layout."""
    bottom = B_MODE_FULL_BOTTOM if mode == "b_only" else B_MODE_SPLIT_BOTTOM
    return (
        B_MODE_SEARCH_LEFT,
        B_MODE_SEARCH_TOP,
        B_MODE_SEARCH_RIGHT,
        bottom,
    )


def find_b_mode_contours(frame, mode):
    """Return the search bounds, binary threshold image, and detected contours."""
    search_bounds = get_b_mode_search_bounds(mode)
    print(
        f"[_find_b_mode] Search bounds=(left={search_bounds[0]}, top={search_bounds[1]},"
        f"right={search_bounds[2]}, bottom={search_bounds[3]})."
    )
    search_area = crop(frame, search_bounds)

    # Use grayscale so each pixel has one value to test.
    gray = cv2.cvtColor(search_area, cv2.COLOR_BGR2GRAY)
    threshold_value, thresholded = cv2.threshold(
        gray,
        CONTOUR_THRESHOLD,
        255,
        cv2.THRESH_BINARY,
    )

    # Find contours of connected bright pixels. The largest contour is assumed to be the B-mode panel.
    contours, _ = cv2.findContours(
        thresholded,
        cv2.RETR_EXTERNAL,  # Outermost contours only
        cv2.CHAIN_APPROX_SIMPLE,  # Store only contour corner points
    )
    print(f"[_find_b_mode] Found {len(contours)} external contours.")
    return search_bounds, thresholded, contours


def _find_b_mode(frame, mode):
    """Detect horizontal B-mode bounds and align vertical bounds to scale ticks."""

    # The panel's x position/width can vary, so detect those from its largest bright contour.
    # The y limits are fixed by the scale ticks and are used both for the contour search and the final crop.
    search_bounds, _, contours = find_b_mode_contours(frame, mode)
    if not contours:
        print("[_find_b_mode] No connected bright regions were found.")
        raise RuntimeError(f"No B-mode window found for display mode {mode!r}.")

    # Compare contour areas and use the largest as the ultrasound panel.
    ranked_contours = sorted(contours, key=cv2.contourArea, reverse=True)
    largest_contour = ranked_contours[0]
    x, y, width, height = cv2.boundingRect(largest_contour)

    # Contour coordinates are local to the cropped search region. Add its left offset for x.
    x1 = x + search_bounds[0]
    y1 = search_bounds[1]
    bounds = (x1, y1, x1 + width, search_bounds[3])
    # print(
    #     f"[_find_b_mode] Selected largest contour (area="
    #     f"{cv2.contourArea(largest_contour):.1f}); full-frame box="
    #     f"(left={bounds[0]}, top={bounds[1]}, right={bounds[2]}, "
    #     f"bottom={bounds[3]}), width={width}, height={bounds[3] - bounds[1]}. "
    #     f"Vertical bounds align with fixed scale ticks at rows "
    #     f"{bounds[1]} and {bounds[3] - 1}."
    # )
    b_mode_crop = crop(frame, bounds)
    return b_mode_crop, bounds


def extract_windows(frame, mode):
    """Return each active view as (cropped image, full-frame bounds)."""
    print(f"[extract_windows] Extracting windows for detected mode={mode!r}.")

    # B-mode is present in every supported layout.
    windows = {"b_mode": _find_b_mode(frame, mode)}

    # The lower view has a known fixed rectangle, so it does not need contour
    # detection. It is included only when that mode is active.
    if mode in ("spectral", "m_mode"):
        print(f"[extract_windows] Mode is {mode!r}; extracting fixed lower window bounds={SPECTRAL_WINDOW}.")
        windows[mode] = (crop(frame, SPECTRAL_WINDOW), SPECTRAL_WINDOW)

    print(f"[extract_windows] Active window names: {list(windows)}.")
    return windows
