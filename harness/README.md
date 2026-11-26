# harness

Runs the pipeline stages as a DAG defined in Python and compares each run
against a baseline.

## Usage

```
source .venv/bin/activate                                          # from the repo root
python harness/src/main.py run harness/conditions/vessels_section.json  # run under a conditions file
python harness/src/main.py run harness/pipelines/vessels.py        # run the pipeline as defined
python harness/src/main.py baseline <run_id>                       # make a run the baseline
python harness/src/main.py order harness/pipelines/vessels.py      # list stages in run order
```

`run` also takes `--run-id NAME` (default: a timestamp).
Exit status: 0 OK, 1 a node failed, 2 output differs from baseline (with `"fail_on_diff": true`).

While it runs, the terminal shows a live row per node: a spinner and timer while
it runs, a progress bar with done/total and time left for stages that report
progress, and ✓ / ✗ / - (skipped) when done, with the error or reason cut to fit.
When the output isn't a terminal (piped, redirected, CI), it prints one line per
node as it finishes instead. The display lives in `harness/src/progress.py`.

Each run writes `harness/output/runs/<run_id>/`:
- `report.md` — status, params used, timings, failures, baseline comparison
- `conditions.json` — the conditions the run used

## Output layout

One folder per node, named
`<step>_<node>` so they sort in run order (nodes that don't depend on each other
share a step). Each holds what the stage wrote plus `log.txt`, what it printed.

```
runs/<run_id>/
  01_extract_frames/recording_oct_5/frame_001800.jpg ...
  02_segment_windows/windows.csv, log.txt
  03_ecg/ecg_summary.csv, ecg_trace.csv, r_peaks.csv, log.txt
  ...
```

Baseline comparison also works against runs made before this layout, which kept
results in `<node>/output/`.

## Conditions files

A conditions file is JSON that says what to run and how. Keep them in
`harness/conditions/`. Example (`harness/conditions/vessels_section.json`):

```json
{
  "pipeline": "harness/pipelines/vessels.py",
  "start": "1:00",
  "end": "1:10",
  "params": {
    "extract_frames": {"fps": 1}
  },
  "compare_to": "baseline",
  "fail_on_diff": false
}
```

Only `pipeline` is required. Paths are relative to the repo root.

| Key | Default | Meaning |
|---|---|---|
| `pipeline` | — | pipeline `.py` file to run |
| `start`, `end` | whole video | run on a section of the video; seconds (`75`, `75.5`) or `"m:ss"` (`"1:15"`). Either can be left out. Passed to every node whose stage takes `start`/`end` params (today: `extract_frames`). |
| `params` | none | per-node param overrides, `{"node": {"param": value}}`. `null` means `None`, e.g. `"fps": null` saves every frame. |
| `compare_to` | `"baseline"` | baseline name or run id to compare against |
| `fail_on_diff` | `false` | exit with status 2 if any output differs from it |

Unknown keys, unknown node names, unreadable times or an `end` before `start`
stop the run before anything executes.

### Running on a section of the video

Frames keep their index in the full video (`frame_001800.jpg` is 60 s in), so
section results line up with a full run. Compared against a full-video baseline,
the frames outside the section show up as "only in other"; to compare sections,
baseline one under its own name and point `compare_to` at it:

```
python harness/src/main.py run harness/conditions/vessels_section.json --run-id s60
python harness/src/main.py baseline s60 --name s60
# then set "compare_to": "s60" in the conditions file
```

Every run re-runs every stage. If a stage fails, the stages downstream of it are skipped.

## Adding a stage (contract)

1. Put the code in `modules/<stage>/src/main.py` and its data in `data/<stage>/`
   (`input/`, `output/`, and `truth/` for hand labels); copy `extract_frames` as a
   template. Name folders after the stage, not a number: the run order comes from
   the pipeline (`order` lists it), so inserting a stage renames nothing.
   With no arguments the stage should read `data/<stage>/input/` and write
   `data/<stage>/output/`: `python modules/<stage>/src/main.py`.
2. Define `run(input, output, **params)` in `src/main.py`:
   - `input`: a file or directory (the upstream stage's output directory).
     If the node has several inputs, a directory with one entry per input,
     named after the upstream node.
   - `output`: an existing, empty directory to write into.
   - Raise an exception on failure (don't call `sys.exit`).
   - Optional: accept `progress=None` and call `progress(done, total)` as you
     work (e.g. once per frame). The harness passes a function that drives the
     node's progress bar; standalone runs pass nothing.
   - Be deterministic: same input + params -> same output.
3. Write results the next stage (and comparators) can read — ideally a CSV keyed
   by image name, plus any images.
   A stage that works on one display window (e.g. the B-mode view) takes
   `inputs=[frames, windows]` and crops each frame using `segment_windows`'
   `windows.csv`, as `detect_circular_vessels` and `measure_diameter` do.
4. Add any new third-party dependency, pinned, to the root `requirements.txt`.
5. Load the stage and add a node in the pipeline file:
   ```python
   crop_view = load_stage("crop_view")   # imports modules/crop_view/src/main.py
   crops = p.node("crop_view", crop_view.run, inputs=[frames], compare=files_diff())
   ```
   Helper files next to `main.py` can be imported normally (`from config import x`).
   Each stage gets its own copies, so two stages can both have a `config.py`.

## Comparators

- `csv_diff(filename, key, columns=None, tolerance=0.0)` — rows matched by key;
  numeric values within `tolerance` count as equal.
- `files_diff(pattern="**/*")` — files compared by name and content hash (the stage's `log.txt` is left out).
- Your own: any function `(current_dir, other_dir) -> Comparison(ok, summary, details)`.

Use one as a node's `compare=` to check it against the baseline. To compare two
versions of a stage, add both as nodes (e.g. with different `params`), or run one,
make it the baseline, and run the other.
