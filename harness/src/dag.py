"""A minimal DAG runner: run each stage in order, then compare against a baseline.

A node wraps a stage's `run(input, output, **params)` function. Its input is a
path (file or directory) or the output directory of an upstream node. A node
with several inputs receives a directory holding one link per input, named
after the upstream node (or the path's file name).

Each run writes, under the harness output directory:
    runs/<run_id>/<node>/output/   what the stage wrote
    runs/<run_id>/<node>/log.txt   everything the stage printed
    runs/<run_id>/report.md        status, timings, failures, comparisons
    baselines/<name>               link to the run used as that baseline
"""
import contextlib
import graphlib
import importlib.util
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from compare import Comparison

REPO_ROOT = Path(__file__).resolve().parents[2]  # harness/src/dag.py -> repo root
MODULES_DIR = REPO_ROOT / "modules"


def load_stage(name, root=MODULES_DIR):
    """Import the stage modules/<name>/src/main.py as a module called `name`.

    Every stage's code is src/main.py, so stages are loaded by file path under
    their folder name rather than imported as `main`. The stage's src/ is put on
    sys.path so it can import helper files next to main.py.
    """
    src = Path(root) / name / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    spec = importlib.util.spec_from_file_location(name, src / "main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(eq=False)
class Node:
    name: str
    fn: Callable
    inputs: list  # of Node | Path
    params: dict = field(default_factory=dict)
    compare: Callable | None = None  # (current_dir, baseline_dir) -> Comparison

    @property
    def upstream(self):
        return [i for i in self.inputs if isinstance(i, Node)]


class Pipeline:
    def __init__(self, name):
        self.name = name
        self.nodes: dict[str, Node] = {}

    def node(self, name, fn, inputs, params=None, compare=None):
        """Add a node. `inputs` is a list of upstream Nodes and/or paths."""
        if name in self.nodes:
            raise ValueError(f"Duplicate node name: {name}")
        node = Node(name, fn, [i if isinstance(i, Node) else Path(i) for i in inputs], params or {}, compare)
        self.nodes[name] = node
        return node

    def steps(self):
        """[(step, node)] in run order. A node's step is one more than its latest
        upstream node's, so nodes sharing a step don't depend on each other."""
        step = {}
        for name, node in self.nodes.items():  # a node is always added after its inputs
            step[name] = 1 + max((step[u.name] for u in node.upstream), default=0)
        return sorted(((step[n], node) for n, node in self.nodes.items()), key=lambda s: s[0])

    def run(self, out_root, run_id=None, baseline=None):
        """Run every node in dependency order, then compare each node that has a
        `compare` against the same node in `baseline` (a run directory).
        Returns (run_dir, statuses, comparisons)."""
        run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = Path(out_root) / "runs" / run_id
        run_dir.mkdir(parents=True)  # fails if the run already exists
        order = graphlib.TopologicalSorter({n: n.upstream for n in self.nodes.values()}).static_order()

        status, notes = {}, {}
        print(f"Run {run_id}: {len(self.nodes)} node(s)")
        for node in order:
            failed_up = [u.name for u in node.upstream if status[u.name] != "ok"]
            if failed_up:
                status[node.name], notes[node.name] = "skipped", f"upstream failed: {', '.join(failed_up)}"
            else:
                status[node.name], notes[node.name] = self._execute(node, run_dir)
            print(f"  {'✓' if status[node.name] == 'ok' else '✗'} {node.name}: {status[node.name]} {notes[node.name]}")

        comparisons = {}
        for node in self.nodes.values():
            base = baseline / node.name / "output" if baseline else None
            if node.compare and status[node.name] == "ok" and base and base.is_dir():
                try:
                    comparisons[node.name] = node.compare(run_dir / node.name / "output", base)
                except Exception as e:
                    comparisons[node.name] = Comparison(False, f"comparison error: {e!r}")

        (run_dir / "report.md").write_text(_report(self.name, run_id, status, notes, baseline, comparisons))
        print(f"Report: {run_dir / 'report.md'}")
        return run_dir, status, comparisons

    def _execute(self, node, run_dir):
        out = run_dir / node.name / "output"
        out.mkdir(parents=True)
        paths = [run_dir / i.name / "output" if isinstance(i, Node) else i for i in node.inputs]
        node_input = paths[0]
        if len(paths) > 1:
            node_input = run_dir / node.name / "input"
            node_input.mkdir()
            for i, p in zip(node.inputs, paths):
                (node_input / (i.name if isinstance(i, Node) else p.name)).symlink_to(p.resolve())
        t0 = time.time()
        with open(run_dir / node.name / "log.txt", "w") as log, \
                contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            try:
                node.fn(node_input, out, **node.params)
            except Exception:
                traceback.print_exc()
                error = traceback.format_exc().strip().splitlines()[-1]
                return "failed", f"{error} (see {node.name}/log.txt)"
        return "ok", f"{time.time() - t0:.1f}s"


def find_run(out_root, name):
    """A baseline name (baselines/<name>) or a run id (runs/<id>) -> run directory, or None."""
    for p in (Path(out_root) / "baselines" / name, Path(out_root) / "runs" / name):
        if p.exists():
            return p.resolve()
    return None


def set_baseline(out_root, run_id, name="baseline"):
    run_dir = Path(out_root) / "runs" / run_id
    if not run_dir.is_dir():
        raise SystemExit(f"No such run: {run_dir}")
    link = Path(out_root) / "baselines" / name
    link.parent.mkdir(parents=True, exist_ok=True)
    link.unlink(missing_ok=True)
    link.symlink_to(run_dir.resolve())


def _report(pipeline, run_id, status, notes, baseline, comparisons):
    lines = [f"# Run {run_id} — pipeline `{pipeline}`", "", "| node | status | |", "|---|---|---|"]
    lines += [f"| {n} | {s} | {notes[n]} |" for n, s in status.items()]
    if comparisons:
        lines += ["", f"## Compared to `{baseline.name}`", ""]
        for name, c in comparisons.items():
            lines.append(f"- {'✓' if c.ok else '✗'} **{name}**: {c.summary}")
            lines += [f"    - {d}" for d in c.details[:20]]
            if len(c.details) > 20:
                lines.append(f"    - … {len(c.details) - 20} more")
    return "\n".join(lines) + "\n"
