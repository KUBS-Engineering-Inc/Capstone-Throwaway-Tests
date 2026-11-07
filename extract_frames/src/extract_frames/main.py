"""Extract frames from video files into individual images using OpenCV.

Usage:
    extract-frames [INPUT] [OUTPUT] [--every N] [--fps F] [--ext jpg|png]

INPUT is a video file or a directory of videos (default: input/).
OUTPUT is a directory (default: output/). Frames from each video go to
OUTPUT/<video name>/, e.g.
input/recording_oct_5.mp4 -> output/recording_oct_5/frame_000000.jpg
"""
import argparse
from pathlib import Path

import cv2

STAGE_DIR = Path(__file__).resolve().parents[2]  # src/extract_frames/main.py -> extract_frames/
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv"}


def extract_frames(video_path, out_dir, every=1, target_fps=None, ext="jpg"):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

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
    return saved


def list_videos(path):
    path = Path(path)
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(p for p in path.iterdir() if p.suffix.lower() in VIDEO_EXTS)
    raise FileNotFoundError(f"Input not found: {path}")


def run(input, output, every=1, fps=None, ext="jpg"):
    """Extract frames from every video under `input` into `output`/<video name>/.
    Returns the total number of frames saved."""
    return sum(extract_frames(video, Path(output) / video.stem, every, fps, ext) for video in list_videos(input))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", nargs="?", default=STAGE_DIR / "input", help="video file or directory of videos (default: input/)")
    p.add_argument("output", nargs="?", default=STAGE_DIR / "output", help="output directory (default: output/)")
    p.add_argument("--every", type=int, default=1, help="save every Nth frame (default: 1)")
    p.add_argument("--fps", type=float, help="target frames per second to save (overrides --every)")
    p.add_argument("--ext", default="jpg", choices=["jpg", "png"], help="image format")
    a = p.parse_args()
    run(a.input, a.output, every=a.every, fps=a.fps, ext=a.ext)


if __name__ == "__main__":
    main()
