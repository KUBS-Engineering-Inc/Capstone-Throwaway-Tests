"""Extract frames from video files into individual images using OpenCV.

Usage:
    python modules/extract_frames/src/main.py [INPUT] [OUTPUT] [--every N] [--fps F] [--ext jpg|png]
                                              [--start SEC] [--end SEC]

INPUT is a video file or a directory of videos (default: data/extract_frames/input/).
OUTPUT is a directory (default: data/extract_frames/output/). Frames from each video go to
OUTPUT/<video name>/, e.g.
input/recording_oct_5.mp4 -> output/recording_oct_5/frame_000000.jpg

--start/--end limit extraction to a section of each video (in seconds). Frames keep
their index in the full video, so a section gives the same files as a full run would
for that time range.
"""
import argparse
from pathlib import Path

import cv2

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "extract_frames"  # modules/extract_frames/src/main.py -> repo root
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv"}


def extract_frames(video_path, out_dir, every=1, target_fps=None, ext="jpg", start=None, end=None):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if target_fps and src_fps:
        every = max(1, round(src_fps / target_fps))

    if (start or end) and not src_fps:
        raise RuntimeError(f"Can't select a time range: {video_path} reports no frame rate")
    first = round(start * src_fps) if start else 0
    stop = round(end * src_fps) if end is not None else None  # exclusive
    if first:
        cap.set(cv2.CAP_PROP_POS_FRAMES, first)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    section = f" from frame {first}" + (f" to {stop}" if stop is not None else "") if first or stop is not None else ""
    print(f"{video_path}: {total} frames @ {src_fps:.2f} fps -> saving every {every} frame(s){section} to {out_dir}/")

    # Count frames from the start of the video so names (and the every-Nth choice)
    # match a full run.
    idx = first
    saved = 0
    while stop is None or idx < stop:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % every == 0:
            cv2.imwrite(str(out_dir / f"frame_{idx:06d}.{ext}"), frame)
            saved += 1
        idx += 1

    cap.release()
    print(f"Done: saved {saved} of {idx - first} frames read.")
    return saved


def list_videos(path):
    path = Path(path)
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(p for p in path.iterdir() if p.suffix.lower() in VIDEO_EXTS)
    raise FileNotFoundError(f"Input not found: {path}")


def run(input, output, every=1, fps=None, ext="jpg", start=None, end=None):
    """Extract frames from every video under `input` into `output`/<video name>/.
    `start`/`end` (seconds) limit it to a section of each video.
    Returns the total number of frames saved."""
    if start is not None and end is not None and end <= start:
        raise ValueError(f"end ({end}) must be after start ({start})")
    return sum(extract_frames(video, Path(output) / video.stem, every, fps, ext, start, end)
               for video in list_videos(input))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", nargs="?", default=DATA_DIR / "input", help="video file or directory of videos (default: data/extract_frames/input/)")
    p.add_argument("output", nargs="?", default=DATA_DIR / "output", help="output directory (default: data/extract_frames/output/)")
    p.add_argument("--every", type=int, default=1, help="save every Nth frame (default: 1)")
    p.add_argument("--fps", type=float, help="target frames per second to save (overrides --every)")
    p.add_argument("--ext", default="jpg", choices=["jpg", "png"], help="image format")
    p.add_argument("--start", type=float, help="start of the section to extract, in seconds (default: 0)")
    p.add_argument("--end", type=float, help="end of the section to extract, in seconds (default: end of video)")
    a = p.parse_args()
    run(a.input, a.output, every=a.every, fps=a.fps, ext=a.ext, start=a.start, end=a.end)


if __name__ == "__main__":
    main()
