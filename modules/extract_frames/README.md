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

We used OpenCV to read the videos because every other stage already depends on it, so frame extraction doesn't add a new dependency or require installing ffmpeg.

Each frame is named after its index in the original video (`frame_000030.jpg` is the 30th frame), even when only some frames are saved. That way any result from a later stage can be traced back to the exact moment in the recording, since the time is the index divided by the video's frame rate. The index is padded to six digits so the files stay in order when sorted by name. Frames from each video go into their own folder, so several recordings can be processed together without their frames mixing.

When `--fps` is used, it is turned into "save every Nth frame" and rounded to a whole number. Frames are only ever skipped, never blended or interpolated, so every saved image is a real frame from the video. The trade-off is that the actual rate can be slightly off from the one requested when the video's frame rate isn't a multiple of it.

Frames are saved as JPEG by default because they are about 3× smaller than PNG (around 150 KB instead of 430 KB for a `recording_oct_5` frame). JPEG compression slightly changes pixel values, so if a later stage needs the exact pixels, use `--ext png` instead.
