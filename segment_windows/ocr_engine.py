import pytesseract

from config import FOOTER_ROI
from image_utils import crop, prep_light_on_dark


def determine_mode(frame):
    """Use footer text to decide which display mode is active."""
    print(f"[determine_mode] Looking for mode text in footer bounds={FOOTER_ROI}.")

    # Only send the footer to OCR; the rest of the screen is irrelevant to
    # identifying the selected display mode.
    footer = crop(frame, FOOTER_ROI)
    print(f"[determine_mode] Footer crop shape={footer.shape}.")

    # PSM 6 tells Tesseract to treat this small footer region as one text block since we already cropped it.
    prepared_footer = prep_light_on_dark(footer)
    print(f"[determine_mode] Calling Tesseract with --psm 6 on image shape={prepared_footer.shape}.")
    text = pytesseract.image_to_string(
        prepared_footer,
        config="--psm 6",
    ).lower()
    print(f"[determine_mode] OCR text after lowercasing: {text!r}.")

    # These keyword checks turn OCR text into one of the layout names expected by the window extractor. 
    # If neither label is present, use the B-only layout as the fallback.
    if "spectral" in text:
        print("[determine_mode] Comparison: 'spectral' is present; selecting spectral mode.")
        return "spectral"
    if "m-mode" in text or "m mode" in text:
        print("[determine_mode] Comparison: 'm-mode' or 'm mode' is present; selecting M-mode.")
        return "m_mode"
    print("[determine_mode] Neither 'spectral' nor 'm-mode' matched; selecting B-only mode.")
    return "b_only"
