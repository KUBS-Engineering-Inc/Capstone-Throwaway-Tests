# window_extractor.py
import cv2
import numpy as np
import config

def extract_windows(frame, mode):
    windows = {}
    
    # 1. Extract Bottom Window (Static)
    if mode in ['spectral', 'm_mode']:
        bw = config.BOTTOM_WINDOW
        windows[mode] = frame[bw['y1']:bw['y2'], bw['x1']:bw['x2']]
        windows[mode + '_coords'] = bw
        
    # 2. Extract B-Mode Window (Dynamic)
    y_max = config.B_MODE_Y_BOTTOM_FULL if mode == 'b_only' else config.B_MODE_Y_BOTTOM_SPLIT
    y_min = config.B_MODE_Y_TOP
    
    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    mask[y_min:y_max, :] = 255
    
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    masked_gray = cv2.bitwise_and(gray, gray, mask=mask)
    
    _, thresh = cv2.threshold(masked_gray, config.CONTOUR_THRESH, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        largest_contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest_contour)
        windows['b_mode'] = frame[y:y+h, x:x+w]
        windows['b_mode_coords'] = {'x1': x, 'y1': y, 'x2': x+w, 'y2': y+h}
        
    return windows