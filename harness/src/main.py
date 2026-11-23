"""Command line for the pipeline test harness.

    python harness/src/main.py run CONDITIONS.json [--run-id ID]
    python harness/src/main.py run PIPELINE.py [--run-id ID]
    python harness/src/main.py baseline RUN_ID [--name NAME]
    python harness/src/main.py order PIPELINE.py

A conditions file says what to run and how (see harness/conditions/):

    {
      "pipeline": "harness/pipelines/vessels.py",
      "start": "1:00",
      "end": "1:10",
      "params": {"extract_frames": {"fps": 1}},
      "compare_to": "baseline",
      "fail_on_diff": false
    }

Only "pipeline" is required. Paths are relative to the repo root.
  start, end    run on a section of the video: seconds (75, 75.5) or "m:ss" ("1:15").
                Passed to every node whose stage takes start/end params (extract_frames).
  params        per-node param overrides, {node: {param: value}}; null means None
                (e.g. "fps": null saves every frame).
  compare_to    baseline name or run id to compare against (default "baseline").
  fail_on_diff  exit with status 2 if any output differs from it (default false).

Running a PIPELINE.py directly is the same as a conditions file holding only
"pipeline". A copy of the conditions is saved in the run as conditions.json.
Results go under harness/output/ (see --out).

Exit status of `run`: 0 = OK, 1 = a node failed, 2 = output differs from the
baseline (only with fail_on_diff).
"""
import argparse
import inspect
import json
import runpy
from pathlib import Path

from dag import Pipeline, find_run, set_baseline

REPO_ROOT = Path(__file__).resolve().parents[2]  # harness/src/main.py -> repo root
DEFAULT_OUT = REPO_ROOT / "harness" / "output"
CONDITION_KEYS = {"pipeline", "start", "end", "params", "compare_to", "fail_on_diff"}


def load_pipeline(path):
    p = runpy.run_path(str(path)).get("pipeline")
    if not isinstance(p, Pipeline):
        raise SystemExit(f"{path} must define a variable `pipeline = Pipeline(...)`")
    return p


def load_conditions(path):
    """A conditions .json file (or a pipeline .py, meaning just that pipeline) -> dict."""
    path = Path(path)
    if path.suffix == ".py":
        return {"pipeline": str(path)}
    try:
        cond = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"Can't read conditions {path}: {e}")
    if not isinstance(cond, dict) or "pipeline" not in cond:
        raise SystemExit(f"{path}: expected a JSON object with at least a \"pipeline\" key")
    unknown = set(cond) - CONDITION_KEYS
    if unknown:
        raise SystemExit(f"{path}: unknown key(s) {', '.join(sorted(unknown))} (allowed: {', '.join(sorted(CONDITION_KEYS))})")
    return cond


def parse_time(value, key):
    """75, 75.5, "75", "1:15" or "0:01:15" -> seconds; None stays None."""
    if value is None:
        return None
    try:
        seconds = 0.0
        for part in str(value).split(":"):
            seconds = seconds * 60 + float(part)
    except ValueError:
        raise SystemExit(f"{key}: expected seconds or \"[h:]mm:ss\", got {value!r}")
    if seconds < 0:
        raise SystemExit(f"{key}: time can't be negative: {value!r}")
    return seconds


def section_overrides(pipeline, start, end):
    """start/end -> overrides for every node whose stage takes start/end."""
    if start is None and end is None:
        return []
    if start is not None and end is not None and end <= start:
        raise SystemExit(f"end ({end:g} s) must be after start ({start:g} s)")
    nodes = [n for n in pipeline.nodes.values()
             if {"start", "end"} <= set(inspect.signature(n.fn).parameters)]
    if not nodes:
        raise SystemExit("start/end: no node in this pipeline takes start/end params")
    return [(n.name, k, v) for n in nodes for k, v in (("start", start), ("end", end)) if v is not None]


def param_overrides(params):
    """{"node": {"param": value}} -> [(node, param, value)]."""
    if not isinstance(params, dict) or not all(isinstance(v, dict) for v in params.values()):
        raise SystemExit('params: expected {"node": {"param": value}}')
    return [(node, k, v) for node, ps in params.items() for k, v in ps.items()]


def apply_overrides(pipeline, overrides):
    for node, param, value in overrides:
        if node not in pipeline.nodes:
            raise SystemExit(f"params: no node {node!r} in pipeline (nodes: {', '.join(pipeline.nodes)})")
        pipeline.nodes[node].params[param] = value


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="harness output directory (default: harness/output)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run a pipeline under the given conditions")
    r.add_argument("conditions", type=Path, help="conditions .json file, or a pipeline .py file to run as defined")
    r.add_argument("--run-id", help="name for this run (default: timestamp)")

    b = sub.add_parser("baseline", help="mark a run as a baseline")
    b.add_argument("run_id")
    b.add_argument("--name", default="baseline")

    o = sub.add_parser("order", help="list a pipeline's stages in run order")
    o.add_argument("pipeline", type=Path, help="pipeline .py file")
    a = ap.parse_args()

    if a.cmd == "run":
        cond = load_conditions(a.conditions)
        pipeline = load_pipeline(REPO_ROOT / cond["pipeline"])
        start, end = parse_time(cond.get("start"), "start"), parse_time(cond.get("end"), "end")
        apply_overrides(pipeline, section_overrides(pipeline, start, end) + param_overrides(cond.get("params", {})))
        compare_to = cond.get("compare_to", "baseline")
        baseline = find_run(a.out, compare_to)
        if baseline is None and compare_to != "baseline":
            raise SystemExit(f"No baseline or run named {compare_to!r}")
        if baseline is None:
            print("No baseline yet; set one with: python harness/src/main.py baseline <run_id>")
        run_dir, status, comparisons = pipeline.run(a.out, run_id=a.run_id, baseline=baseline)
        (run_dir / "conditions.json").write_text(json.dumps(cond, indent=2) + "\n")
        if any(s == "failed" for s in status.values()):
            raise SystemExit(1)
        if cond.get("fail_on_diff") and not all(c.ok for c in comparisons.values()):
            raise SystemExit(2)

    elif a.cmd == "baseline":
        set_baseline(a.out, a.run_id, a.name)
        print(f"Baseline {a.name!r} -> run {a.run_id}")

    elif a.cmd == "order":
        for step, node in load_pipeline(a.pipeline).steps():
            after = ", ".join(u.name for u in node.upstream)
            print(f"{step}. {node.name}" + (f"  (after {after})" if after else ""))


if __name__ == "__main__":
    main()
