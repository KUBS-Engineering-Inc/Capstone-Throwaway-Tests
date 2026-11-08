"""Command line for the pipeline test harness.

    python harness/src/main.py run PIPELINE [--run-id ID] [--compare-to NAME] [--only NODE ...] [--no-cache] [--fail-on-diff]
    python harness/src/main.py baseline RUN_ID [--name NAME]
    python harness/src/main.py runs
    python harness/src/main.py order PIPELINE

PIPELINE is a Python file that defines `pipeline = Pipeline(...)`, e.g.
harness/pipelines/vessels.py. Results go under harness/output/ (see --out).
By default each run is compared to the "baseline" baseline if it exists.

Exit status of `run`: 0 = OK, 1 = a node failed, 2 = output differs from the
baseline (only with --fail-on-diff).
"""
import argparse
import json
import runpy
from pathlib import Path

from dag import Pipeline, set_baseline

HARNESS_DIR = Path(__file__).resolve().parents[1]  # src/main.py -> harness/
DEFAULT_OUT = HARNESS_DIR / "output"


def load_pipeline(path):
    ns = runpy.run_path(str(path))
    p = ns.get("pipeline")
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
    r.add_argument("--no-compare", action="store_true", help="skip comparison to a baseline")
    r.add_argument("--only", nargs="+", metavar="NODE", help="run only these nodes (plus their upstream nodes)")
    r.add_argument("--no-cache", action="store_true", help="re-run every node even if its cache key is unchanged")
    r.add_argument("--fail-on-diff", action="store_true", help="exit with status 2 if any output differs from the baseline")

    b = sub.add_parser("baseline", help="mark a run as a baseline")
    b.add_argument("run_id")
    b.add_argument("--name", default="baseline")

    sub.add_parser("runs", help="list runs and baselines")

    o = sub.add_parser("order", help="list a pipeline's stages in run order")
    o.add_argument("pipeline", type=Path, help="pipeline definition file")
    a = ap.parse_args()

    if a.cmd == "run":
        pipeline = load_pipeline(a.pipeline)
        compare_to = None
        if not a.no_compare:
            exists = (a.out / "baselines" / a.compare_to).exists() or (a.out / "runs" / a.compare_to).exists()
            if exists:
                compare_to = a.compare_to
            elif a.compare_to != "baseline":
                raise SystemExit(f"No baseline or run named {a.compare_to!r}")
            else:
                print("No baseline yet; set one with: python harness/src/main.py baseline <run_id>")
        run_dir = pipeline.run(a.out, run_id=a.run_id, only=a.only, use_cache=not a.no_cache, compare_to=compare_to)
        m = json.loads((run_dir / "manifest.json").read_text())
        if any(r["status"] == "failed" for r in m["nodes"].values()):
            raise SystemExit(1)
        if a.fail_on_diff and not all(c["ok"] for c in m["comparisons"].values()):
            raise SystemExit(2)

    elif a.cmd == "baseline":
        set_baseline(a.out, a.run_id, a.name)
        print(f"Baseline {a.name!r} -> run {a.run_id}")

    elif a.cmd == "order":
        for step, node in load_pipeline(a.pipeline).steps():
            after = ", ".join(u.name for u in node.upstream)
            print(f"{step}. {node.name}" + (f"  (after {after})" if after else ""))

    elif a.cmd == "runs":
        baselines = {}
        if (a.out / "baselines").exists():
            baselines = {p.resolve().name: p.name for p in (a.out / "baselines").iterdir()}
        for run in sorted((a.out / "runs").glob("*")) if (a.out / "runs").exists() else []:
            m = json.loads((run / "manifest.json").read_text()) if (run / "manifest.json").exists() else {}
            status = ", ".join(f"{n}:{r['status']}" for n, r in m.get("nodes", {}).items())
            tag = f"  [baseline: {baselines[run.name]}]" if run.name in baselines else ""
            print(f"{run.name}  {m.get('pipeline', '?')}  {status}{tag}")


if __name__ == "__main__":
    main()
