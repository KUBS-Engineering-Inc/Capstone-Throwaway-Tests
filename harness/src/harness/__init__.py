"""Test harness: run pipeline stages as a DAG, cache their outputs, and compare runs."""
from .compare import Comparison, csv_diff, files_diff
from .pipeline import Node, Pipeline, resolve_run, set_baseline

__all__ = ["Comparison", "Node", "Pipeline", "csv_diff", "files_diff", "resolve_run", "set_baseline"]
