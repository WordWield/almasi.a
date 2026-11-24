# Architecture: Progress

`almasi.Progress(text, stream=None)` replaces the former Spinner class.
It is an ordinary single-operation context, not a service or resource.
The stream defaults to the current sys.stderr. Supply a writable text stream
with isatty() to redirect presentation. No initialization is needed.

```python
import almasi

with almasi.Progress('Checking for updates') as progress:
	progress.update('Downloading')
	# Perform the operation.
	progress.update('Up to date')

progress.update('Verified')
```

The synchronous and asynchronous context protocols both return the Progress
instance. Enter once per operation. A terminal displays an active animation;
normal exit stops it and renders a success mark, while exceptional exit
renders a failure mark and propagates the original exception unchanged.

`update(text: str) -> None` replaces the description, retaining the outcome
after completion. Text must be a single line. On a terminal, post-exit updates
replace the last physical row: the previous text must fit one terminal row
and no other output may have been written beneath it. The caller owns this
condition; Progress does not track arbitrary output or coordinate overlapping
contexts. On a redirected or captured stream, no animation or ANSI escapes
are emitted. Only the final description is printed on exit; later updates
append a corrected outcome because ordinary log streams cannot erase output.

`Progress.skipped(text: str) -> None` reports an already complete operation
on stderr without starting an animation.

Progress owns presentation, not subprocess execution, exception translation,
fallback policy or persisted state. Libraries and Hub can wrap their own
operations directly. Migrate old Spinner callers to Progress and
`progress.update(text)`; the raw yaspin object and custom renderer options
are not part of the new public contract.
