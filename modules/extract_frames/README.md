# Extract Frames

Splits ultrasound recordings into individual frame images. It is the first stage of the vessels pipeline.

## How to Run

From the repo root, with the shared environment active (`source .venv/bin/activate`):

```bash
python modules/extract_frames/src/main.py                     # data/extract_frames/input/ -> output/
python modules/extract_frames/src/main.py INPUT OUTPUT        # INPUT: one video or a folder of videos
python modules/extract_frames/src/main.py --fps 1             # save 1 frame per second of video
```

| Flag | Default | Meaning |
|---|---|---|
| `--every N` | 1 | save every Nth frame |
| `--fps F` | off | save about F frames per second of video (overrides `--every`) |
| `--ext jpg\|png` | `jpg` | image format |

Supported videos: `.mp4`, `.mov`, `.avi`, `.mkv`. Videos are not committed
(they are in `.gitignore`); put them in `data/extract_frames/input/`, e.g.
`recording_oct_5.mp4`.

From Python, or from the harness, call `run(input, output, every=1, fps=None, ext="jpg")`.
The harness's vessels pipeline runs it with `fps=1`.

## What it Does

Splits each video into individual frame images for the later stages.

1. List the videos: INPUT is one video file, or every video in a folder (sorted by name).
2. Open each video with `cv2.VideoCapture` and read its frame rate and frame count.
3. If `--fps` is given, convert it to "every Nth frame": N = round(video fps / target fps).
4. Read the frames in order and save every Nth one.
5. Print how many frames were saved; `run()` returns the total over all videos.

Files written to OUTPUT, one folder per video:

| File | Contents |
|---|---|
| `<video name>/frame_NNNNNN.jpg` | one frame; `NNNNNN` is its index in the original video, zero-padded to 6 digits |

For example, `recording_oct_5.mp4` at `--fps 1` (30 fps video) gives
`recording_oct_5/frame_000000.jpg`, `frame_000030.jpg`, `frame_000060.jpg`, …

## Design Decision

- **OpenCV only:** the other stages already use OpenCV, so frame extraction
  adds no new dependency (no ffmpeg install needed).
- **File name = original frame index:** frames keep their position in the
  video, even when only some are saved, so any result can be traced back to
  its exact time in the recording (time = index / video fps). Six digits keep
  the files sorted in order.
- **One folder per video:** several recordings can be processed together
  without their frames mixing.
- **`--fps` rounds to whole frames:** frames are only skipped, never
  interpolated, so every saved image is an original frame. The real rate can
  differ slightly from the target when the video's fps is not a multiple of it.
- **JPEG by default:** frames are about 3× smaller than PNG (150 KB vs 430 KB
  for a `recording_oct_5` frame). JPEG compression
  slightly changes pixel values; use `--ext png` if a later stage needs exact pixels.
