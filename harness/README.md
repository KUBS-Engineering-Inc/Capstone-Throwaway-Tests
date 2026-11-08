# harness

Runs the pipeline stages as a DAG defined in Python and compares each run
against a baseline.

## Usage

```
source .venv/bin/activate                                       # from the repo root
python harness/src/main.py run harness/pipelines/vessels.py     # run + compare to "baseline" if set
python harness/src/main.py baseline <run_id>                    # make a run the baseline
python harness/src/main.py order harness/pipelines/vessels.py   # list stages in run order
```

Flags for `run`: `--run-id NAME`, `--compare-to RUN_OR_BASELINE`, `--fail-on-diff`.
Exit status: 0 OK, 1 a node failed, 2 output differs from baseline (with `--fail-on-diff`).

Each run writes `harness/output/runs/<run_id>/`:
- `<node>/output/` — what the stage wrote; `<node>/log.txt` — what it printed
- `report.md` — status, timings, failures, baseline comparison

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
   - Be deterministic: same input + params -> same output.
3. Write results the next stage (and comparators) can read — ideally a CSV keyed
   by image name, plus any images.
4. Add any new third-party dependency, pinned, to the root `requirements.txt`.
5. Load the stage and add a node in the pipeline file:
   ```python
   crop_view = load_stage("crop_view")   # imports modules/crop_view/src/main.py
   crops = p.node("crop_view", crop_view.run, inputs=[frames], compare=files_diff())
   ```
   Helper files next to `main.py` can be imported normally (`from utils import x`);
   give them names that won't clash with other stages' helpers.

## Comparators

- `csv_diff(filename, key, columns=None, tolerance=0.0)` — rows matched by key;
  numeric values within `tolerance` count as equal.
- `files_diff(pattern="**/*")` — files compared by name and content hash.
- Your own: any function `(current_dir, other_dir) -> Comparison(ok, summary, details)`.

Use one as a node's `compare=` to check it against the baseline. To compare two
versions of a stage, add both as nodes (e.g. with different `params`), or run one,
make it the baseline, and run the other.
