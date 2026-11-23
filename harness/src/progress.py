"""Live progress display for a pipeline run.

In a terminal, one row per node is redrawn in place:

    ✓ extract_frames                 ━━━━━━━━━━━━━━━━━━━━  300/300  0:00:01
    ⠹ segment_windows                ━━━━━━━━╺━━━━━━━━━━━  142/300  0:00:37  0:00:41
    · detect_circular_vessels                              waiting

When the output isn't a terminal (piped, redirected to a file, CI), it prints
one line per node as it finishes instead.

Stages report progress through an optional `progress(done, total)` argument: if
a stage's run() accepts `progress`, the harness passes it a function to call as
it works. Stages without it just show a spinner and timer.

The display writes to the real terminal (sys.__stdout__) because, while a stage
runs, sys.stdout is redirected into its log.txt.
"""
import sys

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Column
from rich.text import Text

BAR_WIDTH = 20
# Room the columns other than the name and note take up: status, bar, done/total,
# elapsed, remaining, and the spaces between columns.
OTHER_COLUMNS_WIDTH = 1 + BAR_WIDTH + 11 + 7 + 7 + 7
SYMBOLS = {"waiting": "[dim]·", "ok": "[green]✓", "failed": "[red]✗", "skipped": "[yellow]-"}


class _StatusColumn(ProgressColumn):
    """A spinner while the node runs, a symbol once it has finished (or before it starts)."""

    def __init__(self, table_column=None):
        super().__init__(table_column=table_column)
        self.spinner = SpinnerColumn()

    def render(self, task):
        status = task.fields["status"]
        if status == "running":
            return self.spinner.render(task)
        return Text.from_markup(SYMBOLS[status])


class _ShowWhenRunning(ProgressColumn):
    """Wraps a column so it only shows while the node runs or once it has progress."""

    def __init__(self, column, finished=True):
        super().__init__()
        self.column, self.finished = column, finished

    def render(self, task):
        status = task.fields["status"]
        if status == "running" and task.total is not None or status == "ok" and self.finished and task.total:
            return self.column.render(task)
        return Text("")


class _TimeColumn(ProgressColumn):
    def __init__(self):
        super().__init__()
        self.elapsed = TimeElapsedColumn()

    def render(self, task):
        if task.fields["status"] in ("waiting", "skipped"):
            return Text("")
        return self.elapsed.render(task)


class Display:
    """Shows each node's status while a pipeline runs. Use as a context manager."""

    def __init__(self, title, node_names, file=None):
        self.file = file or sys.__stdout__
        self.live = self.file.isatty()
        self.title = title
        if not self.live:
            return
        self.console = Console(file=self.file)
        width = max(map(len, node_names), default=10)
        # Long notes (errors) are cut to fit; the full text is in report.md and log.txt.
        self.note_width = max(10, self.console.width - width - OTHER_COLUMNS_WIDTH)
        fixed = dict(no_wrap=True, overflow="crop")
        self.progress = Progress(
            _StatusColumn(table_column=Column(min_width=1, **fixed)),
            TextColumn("{task.description}", table_column=Column(min_width=width, **fixed)),
            _ShowWhenRunning(BarColumn(bar_width=BAR_WIDTH)),
            _ShowWhenRunning(MofNCompleteColumn()),
            _TimeColumn(),
            _ShowWhenRunning(TimeRemainingColumn(), finished=False),
            TextColumn("{task.fields[note]}", markup=False, style="dim", table_column=Column(**fixed)),
            console=self.console,
            redirect_stdout=False,  # stage output goes to log.txt, not here
            redirect_stderr=False,
            refresh_per_second=8,
        )
        # Nodes start waiting: total=None and not started, so no timer runs yet.
        self.tasks = {n: self.progress.add_task(n, total=None, start=False, status="waiting", note="waiting")
                      for n in node_names}

    def __enter__(self):
        if self.live:
            self.console.print(f"[bold]{self.title}")
            self.progress.start()
        else:
            print(self.title, file=self.file, flush=True)
        return self

    def __exit__(self, *exc):
        if self.live:
            self.progress.stop()

    def start(self, name):
        """Mark a node as running and return its `progress(done, total)` function."""
        if not self.live:
            return lambda done, total: None
        task = self.tasks[name]
        self.progress.start_task(task)
        self.progress.update(task, status="running", note="")

        def progress(done, total):
            self.progress.update(task, completed=done, total=total)
        return progress

    def finish(self, name, status, note=""):
        """Mark a node ok / failed / skipped, with a short note (e.g. the error)."""
        if not self.live:
            symbol = "✓" if status == "ok" else "✗"
            print(f"  {symbol} {name}: {status} {note}", file=self.file, flush=True)
            return
        if len(note) > self.note_width:
            note = note[:self.note_width - 1] + "…"
        task = self.tasks[name]
        self.progress.stop_task(task)
        self.progress.update(task, status=status, note="" if status == "ok" else note)
