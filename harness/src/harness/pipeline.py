"""DAG of pipeline stages: run each node, cache its output, compare against a baseline.

A node wraps a stage's `run(input, output, **params)` function. Its input is
either a path (file or directory) or the output directory of an upstream node.
When a node has several inputs it receives a directory holding one link per
input, named after the upstream node (or the path's file name).

Layout under the harness output directory:
    cache/<node>/<key>/output/   stage output (reused while the key is unchanged)
    cache/<node>/<key>/log.txt   everything the stage printed
    runs/<run_id>/<node>         link to the cache entry used in that run
    runs/<run_id>/manifest.json  per-node status, timing, key, params, errors
    runs/<run_id>/report.md      human-readable summary incl. comparisons
    baselines/<name>             link to the run used as that baseline

The cache key hashes the stage's source code, its params and its inputs'
fingerprints (upstream keys, or path/size/mtime for raw files), so changing a
stage re-runs it and everything downstream of it, and nothing else.
"""
import contextlib
import graphlib
import hashlib
import inspect
import json
import os
import shutil
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .compare import Comparison


@dataclass(eq=False)
class Node:
    name: str
    fn: Callable[..., Any]
    inputs: list  # of Node | Path
    params: dict = field(default_factory=dict)
    compare: Callable[[Path, Path], Comparison] | None = None

    @property
    def upstream(self):
        return [i for i in self.inputs if isinstance(i, Node)]


@dataclass
class ABTest:
    name: str
    a: Node
    b: Node
    compare: Callable[[Path, Path], Comparison]


class Pipeline:
    def __init__(self, name):
        self.name = name
        self.nodes: dict[str, Node] = {}
        self.ab_tests: list[ABTest] = []

    # ---- definition -------------------------------------------------------
    def node(self, name, fn, inputs, params=None, compare=None):
        """Add a node. `inputs` is a list of upstream Nodes and/or paths."""
        if name in self.nodes:
            raise ValueError(f"Duplicate node name: {name}")
        for i in inputs:
            if isinstance(i, Node) and i.name not in self.nodes:
                raise ValueError(f"{name}: input node {i.name!r} is not part of this pipeline")
        node = Node(name, fn, [i if isinstance(i, Node) else Path(i) for i in inputs], params or {}, compare)
        self.nodes[name] = node
        return node

    def ab(self, a, b, compare, name=None):
        """Compare the outputs of two nodes against each other on every run."""
        self.ab_tests.append(ABTest(name or f"{a.name} vs {b.name}", a, b, compare))

    # ---- execution --------------------------------------------------------
    def run(self, out_root, run_id=None, only=None, use_cache=True, compare_to=None):
        """Run the pipeline. Returns the run directory.

        only:       node names to run (their upstream nodes are included).
        use_cache:  reuse outputs whose cache key is unchanged.
        compare_to: baseline name or run id to compare each node against.
        """
        out_root = Path(out_root)
        run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = out_root / "runs" / run_id
        if run_dir.exists():
            raise FileExistsError(f"Run already exists: {run_dir}")
        run_dir.mkdir(parents=True)

        selected = self._with_upstream(only) if only else list(self.nodes.values())
        order = list(graphlib.TopologicalSorter(
            {n: [u for u in n.upstream if u in selected] for n in selected}).static_order())

        keys, results = {}, {}
        print(f"Run {run_id}: {len(order)} node(s)")
        for node in order:
            res = results[node.name] = {"params": _jsonable(node.params),
                                        "inputs": [i.name if isinstance(i, Node) else str(i) for i in node.inputs]}
            failed_up = [u.name for u in node.upstream if results[u.name]["status"] in ("failed", "skipped")]
            if failed_up:
                res.update(status="skipped", error=f"upstream failed: {', '.join(failed_up)}")
                print(f"  - {node.name}: skipped ({res['error']})")
                continue

            key = keys[node] = self._key(node, keys)
            entry = out_root / "cache" / node.name / key
            res["key"] = key
            if use_cache and (entry / "done").exists():
                res.update(status="cached", seconds=0.0)
            else:
                res.update(self._execute(node, entry, run_dir))
            _link(run_dir / node.name, entry)

            mark = {"ran": "✓", "cached": "✓", "failed": "✗"}[res["status"]]
            extra = f" {res['seconds']:.1f}s" if res["status"] == "ran" else ""
            print(f"  {mark} {node.name}: {res['status']}{extra}" + (f" -> {res['error']}" if "error" in res else ""))

        comparisons = self._compare(out_root, run_dir, results, compare_to) if compare_to else {}
        ab = self._ab(run_dir, results)
        manifest = dict(pipeline=self.name, run_id=run_id, nodes=results,
                        compared_to=compare_to, comparisons=comparisons, ab_tests=ab)
        (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        (run_dir / "report.md").write_text(_report(manifest))
        print(f"Report: {run_dir / 'report.md'}")
        return run_dir

    def _execute(self, node, entry, run_dir):
        if entry.exists():
            shutil.rmtree(entry)
        out = entry / "output"
        out.mkdir(parents=True)
        node_input = self._input_path(node, run_dir)
        t0 = time.time()
        with open(entry / "log.txt", "w") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            try:
                ret = node.fn(node_input, out, **node.params)
            except Exception:
                traceback.print_exc()
                return dict(status="failed", seconds=time.time() - t0,
                            error=traceback.format_exc().strip().splitlines()[-1])
        (entry / "done").write_text(datetime.now().isoformat())
        return dict(status="ran", seconds=round(time.time() - t0, 2), returned=_jsonable(ret))

    def _input_path(self, node, run_dir):
        paths = [run_dir / i.name / "output" if isinstance(i, Node) else i for i in node.inputs]
        if len(paths) == 1:
            return paths[0]
        staging = run_dir / "_inputs" / node.name
        staging.mkdir(parents=True)
        for i, p in zip(node.inputs, paths):
            _link(staging / (i.name if isinstance(i, Node) else p.name), p)
        return staging

    def _key(self, node, keys):
        h = hashlib.sha256()
        h.update(_code_fingerprint(node.fn).encode())
        h.update(json.dumps(_jsonable(node.params), sort_keys=True).encode())
        for i in node.inputs:
            h.update((keys[i] if isinstance(i, Node) else _path_fingerprint(i)).encode())
        return h.hexdigest()[:16]

    def _with_upstream(self, names):
        missing = set(names) - set(self.nodes)
        if missing:
            raise KeyError(f"Unknown node(s): {', '.join(sorted(missing))}")
        seen, stack = [], [self.nodes[n] for n in names]
        while stack:
            n = stack.pop()
            if n not in seen:
                seen.append(n)
                stack.extend(n.upstream)
        return seen

    # ---- comparison -------------------------------------------------------
    def _compare(self, out_root, run_dir, results, compare_to):
        base_dir = resolve_run(out_root, compare_to)
        base = json.loads((base_dir / "manifest.json").read_text())["nodes"]
        out = {}
        for name, res in results.items():
            node = self.nodes[name]
            if node.compare is None or res["status"] not in ("ran", "cached"):
                continue
            b = base.get(name)
            if not b or b.get("status") not in ("ran", "cached"):
                out[name] = Comparison(True, "new (not in baseline)").to_dict()
            elif b.get("key") == res["key"]:
                out[name] = Comparison(True, "unchanged (same cache key)").to_dict()
            else:
                out[name] = _safe_compare(node.compare, run_dir / name / "output", base_dir / name / "output")
        return out

    def _ab(self, run_dir, results):
        out = {}
        for t in self.ab_tests:
            if all(results.get(n.name, {}).get("status") in ("ran", "cached") for n in (t.a, t.b)):
                out[t.name] = _safe_compare(t.compare, run_dir / t.a.name / "output", run_dir / t.b.name / "output")
        return out


# ---- helpers --------------------------------------------------------------
def resolve_run(out_root, name):
    """A baseline name (baselines/<name>) or a run id (runs/<id>) -> run directory."""
    out_root = Path(out_root)
    for p in (out_root / "baselines" / name, out_root / "runs" / name):
        if p.exists():
            return p.resolve()
    raise FileNotFoundError(f"No baseline or run named {name!r} under {out_root}")


def set_baseline(out_root, run_id, name="baseline"):
    run_dir = Path(out_root) / "runs" / run_id
    if not (run_dir / "manifest.json").exists():
        raise FileNotFoundError(f"No such run: {run_dir}")
    (Path(out_root) / "baselines").mkdir(parents=True, exist_ok=True)
    _link(Path(out_root) / "baselines" / name, run_dir, replace=True)


def _safe_compare(fn, current, baseline):
    try:
        return fn(current, baseline).to_dict()
    except Exception as e:
        return Comparison(False, f"comparison error: {e!r}").to_dict()


def _link(link, target, replace=False):
    link = Path(link)
    if replace and (link.is_symlink() or link.exists()):
        link.unlink()
    link.symlink_to(os.path.relpath(Path(target).resolve(), link.parent.resolve()), target_is_directory=True)


def _code_fingerprint(fn):
    """Hash every .py file in the package that defines fn (so helper modules count too)."""
    src = Path(inspect.getsourcefile(fn)).resolve()
    pkg = src.parent if (src.parent / "__init__.py").exists() else None
    files = sorted(pkg.rglob("*.py")) if pkg else [src]
    h = hashlib.sha256()
    for f in files:
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def _path_fingerprint(path):
    """Cheap fingerprint of a raw input: relative path, size and mtime of every file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Pipeline input not found: {path}")
    files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
    h = hashlib.sha256(str(path.resolve()).encode())
    for f in files:
        st = f.stat()
        h.update(f"{f.relative_to(path) if f != path else f.name}:{st.st_size}:{st.st_mtime_ns}".encode())
    return h.hexdigest()


def _jsonable(v):
    try:
        json.dumps(v)
        return v
    except TypeError:
        return repr(v)


def _report(m):
    lines = [f"# Run {m['run_id']} — pipeline `{m['pipeline']}`", ""]
    lines += ["| node | status | time | key | params |", "|---|---|---|---|---|"]
    for name, r in m["nodes"].items():
        t = f"{r['seconds']:.1f}s" if r.get("status") == "ran" else ""
        lines.append(f"| {name} | {r['status']} | {t} | `{r.get('key', '')}` | `{json.dumps(r['params'])}` |")
    failed = {n: r for n, r in m["nodes"].items() if r["status"] in ("failed", "skipped")}
    if failed:
        lines += ["", "## Failures", ""]
        lines += [f"- **{n}**: {r.get('error', '')}" + (f" (see `{n}/log.txt`)" if r["status"] == "failed" else "")
                  for n, r in failed.items()]
    for title, section in ((f"Compared to `{m['compared_to']}`", m["comparisons"]), ("A/B tests", m["ab_tests"])):
        if not section:
            continue
        lines += ["", f"## {title}", ""]
        for name, c in section.items():
            lines.append(f"- {'✓' if c['ok'] else '✗'} **{name}**: {c['summary']}")
            lines += [f"    - {d}" for d in c["details"][:20]]
            if len(c["details"]) > 20:
                lines.append(f"    - … {len(c['details']) - 20} more")
    return "\n".join(lines) + "\n"
