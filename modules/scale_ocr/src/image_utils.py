"""ROI cropping and OCR preprocessing, ported from scale_ocr/test_ocr.ipynb."""
import cv2

from config import BORDER, REF_H, REF_W, ROIS, UPSCALE


def scaled_roi(img, name):
    h, w = img.shape[:2]
    x0, y0, x1, y1 = ROIS[name]
    sx, sy = w / REF_W, h / REF_H
    return int(x0 * sx), int(y0 * sy), int(x1 * sx), int(y1 * sy)


def crop(img, name):
    x0, y0, x1, y1 = scaled_roi(img, name)
    return img[y0:y1, x0:x1], (x0, y0)


def prep_light_on_dark(roi_bgr):
    """White/grey text on black -> black text on white, upscaled and binarised."""
    gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=UPSCALE, fy=UPSCALE, interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th = cv2.bitwise_not(th)
    return cv2.copyMakeBorder(th, BORDER, BORDER, BORDER, BORDER, cv2.BORDER_CONSTANT, value=255)
