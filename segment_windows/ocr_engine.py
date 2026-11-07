# ocr_engine.py
import pytesseract
import cv2
import re
import numpy as np
from config import UPSCALE
from image_utils import crop, prep_light_on_dark

def determine_mode(frame):
    # 1. Crop the footer region using the dynamic scaler
    roi_bgr, _ = crop(frame, "footer")
    
    # 2. Prep the image
    prepped = prep_light_on_dark(roi_bgr)
    
    # 3. Run OCR (psm 6 assumes a uniform block of text)
    text = pytesseract.image_to_string(prepped, config="--psm 6").lower()
    
    # 4. Check for the specific mode keywords
    if 'spectral' in text: 
        return 'spectral'
    elif 'm-mode' in text or 'm mode' in text: 
        return 'm_mode'
    else: 
        # Fallback to B-Mode (often labeled as "2D" in the footer)
        return 'b_only'
    
def ocr_words(prepped, offset, psm=11, whitelist=None):
    cfg = f"--oem 3 --psm {psm}"
    if whitelist: cfg += f" -c tessedit_char_whitelist={whitelist}"
    data = pytesseract.image_to_data(prepped, config=cfg, output_type=pytesseract.Output.DICT)
    
    words, ox, oy = [], offset[0], offset[1]
    for i, txt in enumerate(data["text"]):
        txt = txt.strip()
        if not txt or float(data["conf"][i]) < 0: continue
        
        # Calculate coordinates back to original unscaled image pixels
        x = (data["left"][i] - 10) / UPSCALE + ox
        y = (data["top"][i] - 10) / UPSCALE + oy
        words.append({"text": txt, "cy": y + ((data["height"][i] / UPSCALE) / 2)})
    return words

def fit_axis(words):
    pts = []
    for w in words:
        m = re.fullmatch(r"-?\d+", w["text"])
        if m: pts.append((w["cy"], int(w["text"])))
        
    if len(pts) < 2: return None
    ys, vals = zip(*pts)
    a, b = np.polyfit(ys, vals, 1)
    return a, b