"""Comparators: functions (current_dir, other_dir) -> Comparison.

Use them as a node's `compare=` (current run vs baseline) or in Pipeline.ab()
(node A vs node B in the same run). Write your own with the same signature.
"""
import csv
import hashlib
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Comparison:
    ok: bool
    summary: str
    details: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def csv_diff(filename, key, columns=None, tolerance=0.0):
    """Compare a CSV the stage writes, matching rows by `key`.

    key:       column name or tuple of names identifying a row. Several rows may
               share a key (e.g. several detections per image); they are then
               compared in order.
    columns:   columns to compare (default: all shared columns).
    tolerance: max absolute difference for numeric values to count as equal.
    """
    keys = (key,) if isinstance(key, str) else tuple(key)

    def compare(current: Path, other: Path) -> Comparison:
        cur, oth = _read(current / filename, keys), _read(other / filename, keys)
        cols = columns
        if cols is None:
            cur_cols = {c for rows in cur.values() for r in rows for c in r}
            oth_cols = {c for rows in oth.values() for r in rows for c in r}
            cols = sorted((cur_cols & oth_cols) - set(keys))
        details = []
        added, removed = sorted(set(cur) - set(oth)), sorted(set(oth) - set(cur))
        details += [f"only in current: {_fmt(k)}" for k in added]
        details += [f"only in other: {_fmt(k)}" for k in removed]
        changed = 0
        for k in sorted(set(cur) & set(oth)):
            a, b = cur[k], oth[k]
            if len(a) != len(b):
                changed += 1
                details.append(f"{_fmt(k)}: {len(a)} row(s) vs {len(b)}")
                continue
            diffs = [f"{c}: {rb.get(c)} -> {ra.get(c)}" for ra, rb in zip(a, b) for c in cols
                     if not _equal(ra.get(c), rb.get(c), tolerance)]
            if diffs:
                changed += 1
                details.append(f"{_fmt(k)}: " + "; ".join(diffs))
        total = len(set(cur) | set(oth))
        n_diff = len(added) + len(removed) + changed
        summary = (f"{filename}: identical ({total} keys)" if n_diff == 0 else
                   f"{filename}: {n_diff}/{total} keys differ "
                   f"({changed} changed, {len(added)} added, {len(removed)} removed)")
        return Comparison(n_diff == 0, summary, details)

    return compare


def files_diff(pattern="**/*"):
    """Compare the files a stage writes by name and content hash."""

    def compare(current: Path, other: Path) -> Comparison:
        cur, oth = _hashes(current, pattern), _hashes(other, pattern)
        added, removed = sorted(set(cur) - set(oth)), sorted(set(oth) - set(cur))
        changed = sorted(f for f in set(cur) & set(oth) if cur[f] != oth[f])
        details = ([f"only in current: {f}" for f in added] + [f"only in other: {f}" for f in removed]
                   + [f"changed: {f}" for f in changed])
        n = len(added) + len(removed) + len(changed)
        summary = (f"files identical ({len(cur)})" if n == 0 else
                   f"{n} file(s) differ ({len(changed)} changed, {len(added)} added, {len(removed)} removed)")
        return Comparison(n == 0, summary, details)

    return compare


def _read(path, keys):
    rows = defaultdict(list)
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows[tuple(r[k] for k in keys)].append(r)
    return rows


def _hashes(root, pattern):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(root).glob(pattern)) if p.is_file()}


def _equal(a, b, tol):
    if a == b:
        return True
    try:
        x, y = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return math.isclose(x, y, abs_tol=tol) or (math.isnan(x) and math.isnan(y))


def _fmt(k):
    return k[0] if len(k) == 1 else str(k)
