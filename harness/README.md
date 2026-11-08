# harness

Runs the pipeline stages as a DAG defined in Python, caches each stage's output,
and compares every run against a baseline (and stages against each other).

## Usage

```
source .venv/bin/activate                       # from the repo root
harness run harness/pipelines/vessels.py        # run + compare to "baseline" if set
harness baseline <run_id>                       # make a run the baseline
harness runs                                    # list runs
```

Useful flags for `harness run`: `--run-id NAME`, `--only NODE ...` (plus its
upstream nodes), `--no-cache`, `--compare-to RUN_OR_BASELINE`, `--fail-on-diff`.
Exit status: 0 OK, 1 a node failed, 2 output differs from baseline (with `--fail-on-diff`).

Each run writes `harness/output/runs/<run_id>/`:
- `<node>/output/` — what the stage wrote; `<node>/log.txt` — what it printed
- `report.md` — status, timings, baseline comparison, A/B results
- `manifest.json` — the same, machine-readable

A node only re-runs when its code, params or inputs change; everything
downstream of a change re-runs, nothing else does.

## Adding a stage (contract)

1. Make a folder with `pyproject.toml`, `src/<package>/main.py`, `input/`, `output/`
   (copy `extract_frames/` as a template).
2. Expose `run(input, output, **params)` in `<package>/__init__.py`:
   - `input`: a file or directory (the upstream stage's output directory).
     If the node has several inputs, a directory with one entry per input,
     named after the upstream node.
   - `output`: an existing, empty directory to write into.
   - Raise an exception on failure (don't call `sys.exit`).
   - Be deterministic: same input + params -> same output.
3. Write results the next stage (and comparators) can read — ideally a CSV keyed
   by image name, plus any images.
4. Add `-e ./<stage>` to the root `requirements.txt` and `pip install -r requirements.txt`.
5. Add a node in the pipeline file:
   ```python
   crops = p.node("crop_view", crop_view.run, inputs=[frames], compare=files_diff())
   ```

## Comparators

- `csv_diff(filename, key, columns=None, tolerance=0.0)` — rows matched by key;
  numeric values within `tolerance` count as equal.
- `files_diff(pattern="**/*")` — files compared by name and content hash.
- Your own: any function `(current_dir, other_dir) -> Comparison(ok, summary, details)`.

Use one as a node's `compare=` (vs the baseline), or `p.ab(node_a, node_b, comparator)`
to compare two versions of a stage in the same run.
