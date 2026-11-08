"""Command line for the pipeline test harness.

    python harness/src/main.py run PIPELINE [--run-id ID] [--compare-to NAME] [--fail-on-diff]
    python harness/src/main.py baseline RUN_ID [--name NAME]
    python harness/src/main.py order PIPELINE

PIPELINE is a Python file that defines `pipeline = Pipeline(...)`, e.g.
harness/pipelines/vessels.py. Results go under harness/output/ (see --out).
Each run is compared to the baseline named "baseline" if it exists.

Exit status of `run`: 0 = OK, 1 = a node failed, 2 = output differs from the
baseline (only with --fail-on-diff).
"""
import argparse
import runpy
from pathlib import Path

from dag import Pipeline, find_run, set_baseline

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "output"  # src/main.py -> harness/output


def load_pipeline(path):
    p = runpy.run_path(str(path)).get("pipeline")
    if not isinstance(p, Pipeline):
        raise SystemExit(f"{path} must define a variable `pipeline = Pipeline(...)`")
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="harness output directory (default: harness/output)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run a pipeline")
    r.add_argument("pipeline", type=Path, help="pipeline definition file")
    r.add_argument("--run-id", help="name for this run (default: timestamp)")
    r.add_argument("--compare-to", default="baseline", help="baseline name or run id (default: baseline)")
    r.add_argument("--fail-on-diff", action="store_true", help="exit with status 2 if any output differs from the baseline")

    b = sub.add_parser("baseline", help="mark a run as a baseline")
    b.add_argument("run_id")
    b.add_argument("--name", default="baseline")

    o = sub.add_parser("order", help="list a pipeline's stages in run order")
    o.add_argument("pipeline", type=Path, help="pipeline definition file")
    a = ap.parse_args()

    if a.cmd == "run":
        pipeline = load_pipeline(a.pipeline)
        baseline = find_run(a.out, a.compare_to)
        if baseline is None and a.compare_to != "baseline":
            raise SystemExit(f"No baseline or run named {a.compare_to!r}")
        if baseline is None:
            print("No baseline yet; set one with: python harness/src/main.py baseline <run_id>")
        _, status, comparisons = pipeline.run(a.out, run_id=a.run_id, baseline=baseline)
        if any(s == "failed" for s in status.values()):
            raise SystemExit(1)
        if a.fail_on_diff and not all(c.ok for c in comparisons.values()):
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
