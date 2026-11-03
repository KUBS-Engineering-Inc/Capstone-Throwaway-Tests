"""Extract frames from a video file into individual images using OpenCV.

Usage:
    python extract_frames.py VIDEO [--out DIR] [--every N] [--fps F] [--ext jpg|png]

Frames are written to output/<video name>/ by default, e.g.
videos/recording_oct_5.mp4 -> output/recording_oct_5/frame_000000.jpg
"""
import argparse
from pathlib import Path

import cv2

OUTPUT_ROOT = Path(__file__).resolve().parent / "output"


def extract_frames(video_path, out_dir, every=1, target_fps=None, ext="jpg"):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise SystemExit(f"Could not open video: {video_path}")

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if target_fps and src_fps:
        every = max(1, round(src_fps / target_fps))

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"{video_path}: {total} frames @ {src_fps:.2f} fps -> saving every {every} frame(s) to {out_dir}/")

    idx = saved = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % every == 0:
            cv2.imwrite(str(out_dir / f"frame_{idx:06d}.{ext}"), frame)
            saved += 1
        idx += 1

    cap.release()
    print(f"Done: saved {saved} of {idx} frames.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("video", help="path to input video")
    p.add_argument("--out", help="output directory (default: output/<video name>)")
    p.add_argument("--every", type=int, default=1, help="save every Nth frame (default: 1)")
    p.add_argument("--fps", type=float, help="target frames per second to save (overrides --every)")
    p.add_argument("--ext", default="jpg", choices=["jpg", "png"], help="image format")
    a = p.parse_args()
    out = a.out or OUTPUT_ROOT / Path(a.video).stem
    extract_frames(a.video, out, a.every, a.fps, a.ext)


if __name__ == "__main__":
    main()
