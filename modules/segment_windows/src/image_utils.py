import cv2

from config import OCR_UPSCALE


def crop(image, bounds):
    """Return the pixels inside (left, top, right, bottom) bounds."""
    x1, y1, x2, y2 = bounds
    cropped = image[y1:y2, x1:x2]
    print(
        f"[crop] bounds=(left={x1}, top={y1}, right={x2}, bottom={y2}); "
        f"input shape={image.shape}; output crop shape={cropped.shape}"
    )
    return cropped


def prep_light_on_dark(image):
    """Convert bright-on-dark text to OCR-friendly dark text on a light field (OCR was predominantly trained on dark text on light)."""
    print(f"[prep_light_on_dark] Starting with BGR image shape={image.shape}.")

    # Tesseract gets a single brightness value per pixel instead of three color channels.
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    print(f"[prep_light_on_dark] Grayscale shape={gray.shape}.")

    # Scale both dimensions by OCR_UPSCALE to make small footer letters larger.
    gray = cv2.resize(
        gray,
        None,
        fx=OCR_UPSCALE,
        fy=OCR_UPSCALE,
        interpolation=cv2.INTER_CUBIC,
    )
    print(f"[prep_light_on_dark] Resized by {OCR_UPSCALE}x in each dimension; shape={gray.shape}.")

    # Smooth tiny pixel variations before finding a black/white cutoff.
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    threshold_value, binary = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )
    print(f"[prep_light_on_dark] Otsu chose cutoff={threshold_value:.1f}; thresholding separates dark and light pixels.")

    # The inversion makes bright text dark, which is the common OCR input style.
    binary = cv2.bitwise_not(binary)

    # Adds border to prevent Tesseract from cutting off letters that touch the edge of the image.
    prepared = cv2.copyMakeBorder(
        binary,
        10,
        10,
        10,
        10,
        cv2.BORDER_CONSTANT,
        value=255,
    )
    print(
        f"[prep_light_on_dark] Inverted image and added a 10-pixel white border; OCR input shape={prepared.shape}."
    )
    return prepared
