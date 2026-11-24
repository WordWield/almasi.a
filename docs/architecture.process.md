# Architecture: Process

`almasi.Process` is an ordinary instance, not a Module, Singleton or Resource.
Each instance owns one local OS child. Hub owns the collection and restart
policy, not pipe capture or the child's lifecycle.

```python
import almasi
import sys

process = almasi.Process([sys.executable, '-c', 'print("hello")'])
subscription = process.stdout.subscribe(print)
process.start()
assert process.wait(timeout=10) == 0
assert process.stdout.read() == b'hello\n'
process.stdout.unsubscribe(subscription)
```

## Public API

- `Process(command, cwd=None, env=None, max_bytes=None)`: a subprocess command
  (executable string or sequence of argument strings), optional working
  directory, environment mapping replacing the inherited environment when
  supplied, and optional byte retention limit per output stream. Shell
  expansion is not performed.
- `start() -> None`: launch once; OS launch errors propagate and leave the
  instance unstarted. A successful launch cannot be repeated. On POSIX,
  each child starts in its own session, so terminal Ctrl+C reaches its
  supervisor rather than interrupting the child independently.
- `stop(sig=signal.SIGTERM) -> None`: send the selected OS signal to the
  direct child, without waiting. No effect before launch or after exit.
  The default remains SIGTERM; a supervisor of Python children can select
  `signal.SIGINT` to request their ordinary interrupt shutdown. Signal
  support is platform-dependent. The child owns its cleanup; this method
  cannot guarantee it. A child can ignore a signal, so callers must use
  an appropriate timeout when waiting. Descendants are not signaled.
- `wait(timeout=None) -> int`: block until the child exits, both output pipes
  have drained and the final state notification has finished. Timeout raises
  subprocess.TimeoutExpired. A capture or background notification error is
  raised as RuntimeError with its original cause. Call after start returns,
  outside callbacks. A descendant retaining an inherited output pipe may
  postpone EOF even after the direct child exits.
- `stdin`: the native unbuffered binary subprocess pipe, available after
  launch. `write(data)` returns the number of bytes accepted; callers must
  handle partial writes and broken pipes. `close()` sends EOF.
- `stdout`, `stderr`: stable `almasi.resources.Log` instances (Stream subclasses). Read and
  subscribe before or after launch. Only the process producer writes or
  closes them. History remains readable after completion. Use ordinary byte
  reads or `read(since=timestamp)` for timestamped capture chunks; explicit
  `since=None` selects all retained entries. See architecture.resource.md.
- `state`: stable `almasi.resources.Writable` containing a mapping with
  `status` ('created', 'running', 'exited', or 'failed') and `returncode`
  (None before exit, integer afterward). A nonzero child exit is still
  'exited'; 'failed' indicates output capture or cleanup failure.
  Only Process writes state; consumers treat the returned value as read-only.

Each output pipe is drained independently, regardless of subscriptions.
The start notification runs on the calling thread; output and completion
notifications run synchronously on producer threads. Callbacks must return
promptly and must not wait for the child or perform blocking pipe writes.
A failing output callback follows the direct Resource error contract:
capture fails, the child is killed and wait reports the error. A callback
exception during the running notification propagates to start, but the
already launched child is still drained and monitored. A final state
callback failure is reported by wait without changing the published state.
Use explicit stop/wait to manage the lifetime of a launched child.
