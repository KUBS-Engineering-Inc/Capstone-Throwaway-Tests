"""A minimal DAG runner: run each stage in order, then compare against a baseline.

A node wraps a stage's `run(input, output, **params)` function. Its input is a
path (file or directory) or the output folder of an upstream node. A node
with several inputs receives a temporary directory holding one link per input,
named after the upstream node (or the path's file name).

Each run writes, under the harness output directory:
    runs/<run_id>/<step>_<node>/   what the stage wrote, plus log.txt (everything it printed)
    runs/<run_id>/report.md        status, timings, failures, comparisons
    baselines/<name>               link to the run used as that baseline
<step> is the node's step in run order (see Pipeline.steps), two digits.
With layout="frames" the stage folders are split up by frame afterwards; see
layout.py.
"""
import contextlib
import graphlib
import importlib.util
import inspect
import shutil
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from compare import Comparison
from layout import LOG_NAME, LOGS, assemble_stage, frame_keys, is_frame_layout, split_by_frame, stage_dir
from progress import Display

LAYOUTS = ("stages", "frames")

REPO_ROOT = Path(__file__).resolve().parents[2]  # harness/src/dag.py -> repo root
MODULES_DIR = REPO_ROOT / "modules"


def load_stage(name, root=MODULES_DIR):
    """Import the stage modules/<name>/src/main.py as a module called `name`.

    Every stage's code is src/main.py, so stages are loaded by file path under
    their folder name rather than imported as `main`. The stage's src/ is on
    sys.path while it loads so it can import helper files next to main.py.
    Those helpers are then dropped from the module cache, so two stages can
    each have their own `config.py` without one getting the other's.
    """
    src = (Path(root) / name / "src").resolve()
    before = set(sys.modules)
    sys.path.insert(0, str(src))
    try:
        spec = importlib.util.spec_from_file_location(name, src / "main.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(src))
        for mod in set(sys.modules) - before - {name}:
            file = getattr(sys.modules[mod], "__file__", None)
            if file and Path(file).resolve().is_relative_to(src):
                del sys.modules[mod]
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

    def folders(self):
        """{node name: its folder name in a run, <step>_<node>}."""
        return {node.name: f"{step:02d}_{node.name}" for step, node in self.steps()}

    def run(self, out_root, run_id=None, baseline=None, layout="stages"):
        """Run every node in dependency order, then compare each node that has a
        `compare` against the same node in `baseline` (a run directory, in
        either layout). With layout="frames", then split the results by frame.
        Returns (run_dir, statuses, comparisons)."""
        if layout not in LAYOUTS:
            raise ValueError(f"layout must be one of {LAYOUTS}, got {layout!r}")
        run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = Path(out_root) / "runs" / run_id
        run_dir.mkdir(parents=True)  # fails if the run already exists
        order = list(graphlib.TopologicalSorter({n: n.upstream for n in self.nodes.values()}).static_order())
        folders = self.folders()
        dirs = {name: run_dir / folder for name, folder in folders.items()}
        log_paths = {name: (f"{LOGS}/{folder}.txt" if layout == "frames" else f"{folder}/{LOG_NAME}")
                     for name, folder in folders.items()}

        status, notes = {}, {}
        # Logs and multi-input links stay out of the stage folders while the
        # pipeline runs, so no stage sees another stage's log in its input.
        with tempfile.TemporaryDirectory(prefix=f"harness-{run_id}-") as tmp, \
                Display(f"Run {run_id} — pipeline {self.name}: {len(self.nodes)} node(s)",
                        [n.name for n in order]) as display:
            tmp = Path(tmp)
            for node in order:
                failed_up = [u.name for u in node.upstream if status[u.name] != "ok"]
                if failed_up:
                    status[node.name], notes[node.name] = "skipped", f"upstream failed: {', '.join(failed_up)}"
                else:
                    progress = display.start(node.name)
                    status[node.name], notes[node.name] = self._execute(
                        node, dirs, tmp, run_dir / ".logs", log_paths[node.name], progress)
                display.finish(node.name, status[node.name], notes[node.name])

            comparisons = {}
            for node in self.nodes.values():
                if not (node.compare and status[node.name] == "ok" and baseline):
                    continue
                try:
                    base = _stage_view(baseline, node.name, tmp / "baseline" / node.name)
                    if base is not None:
                        comparisons[node.name] = node.compare(dirs[node.name], base)
                except Exception as e:
                    comparisons[node.name] = Comparison(False, f"comparison error: {e!r}")

        # Logs wait in .logs/ until every stage has run (and stay there if the run crashes).
        for name, d in dirs.items():
            if (run_dir / ".logs" / f"{name}.txt").is_file():
                shutil.move(run_dir / ".logs" / f"{name}.txt", d / LOG_NAME)
        shutil.rmtree(run_dir / ".logs", ignore_errors=True)

        if layout == "frames":
            sources = [dirs[n.name] for n in self.nodes.values() if not n.upstream and dirs[n.name].is_dir()]
            split_by_frame(run_dir, {folders[n]: d for n, d in dirs.items()}, frame_keys(sources))

        (run_dir / "report.md").write_text(_report(self, run_id, status, notes, baseline, comparisons, layout))
        print(f"Report: {run_dir / 'report.md'}")
        return run_dir, status, comparisons

    def _execute(self, node, dirs, tmp, log_dir, log_path, progress=None):
        out = dirs[node.name]
        out.mkdir(parents=True)
        paths = [dirs[i.name] if isinstance(i, Node) else i for i in node.inputs]
        node_input = paths[0]
        if len(paths) > 1:
            node_input = tmp / "inputs" / node.name
            node_input.mkdir(parents=True)
            for i, p in zip(node.inputs, paths):
                (node_input / (i.name if isinstance(i, Node) else p.name)).symlink_to(p.resolve())
        params = dict(node.params)
        # A stage that accepts `progress` gets a progress(done, total) function to call as it works.
        if progress and "progress" not in params and "progress" in inspect.signature(node.fn).parameters:
            params["progress"] = progress
        t0 = time.time()
        log_dir.mkdir(exist_ok=True)
        with open(log_dir / f"{node.name}.txt", "w") as log, \
                contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            try:
                node.fn(node_input, out, **params)
            except Exception:
                traceback.print_exc()
                error = traceback.format_exc().strip().splitlines()[-1]
                return "failed", f"{error} (see {log_path})"
        return "ok", f"{time.time() - t0:.1f}s"


def _stage_view(run_dir, name, scratch):
    """Node `name`'s results in a run of either layout, as a stage folder: the
    folder itself, or for a frame-layout run a copy rebuilt in `scratch`.
    None if the run has nothing for that node."""
    if is_frame_layout(run_dir):
        return assemble_stage(run_dir, name, scratch)
    return stage_dir(run_dir, name)


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


def _report(pipeline, run_id, status, notes, baseline, comparisons, layout="stages"):
    lines = [f"# Run {run_id} — pipeline `{pipeline.name}`", "",
             f"Layout: {'by frame (frames/, shared/, logs/)' if layout == 'frames' else 'by stage'}", "",
             "| node | status | params | |", "|---|---|---|---|"]
    lines += [f"| {n} | {s} | {_params(pipeline.nodes[n].params)} | {notes[n]} |" for n, s in status.items()]
    if comparisons:
        lines += ["", f"## Compared to `{baseline.name}`", ""]
        for name, c in comparisons.items():
            lines.append(f"- {'✓' if c.ok else '✗'} **{name}**: {c.summary}")
            lines += [f"    - {d}" for d in c.details[:20]]
            if len(c.details) > 20:
                lines.append(f"    - … {len(c.details) - 20} more")
    return "\n".join(lines) + "\n"


def _params(params):
    return ", ".join(f"{k}={v!r}" for k, v in params.items()) or "—"
