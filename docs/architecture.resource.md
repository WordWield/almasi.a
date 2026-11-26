# Architecture: Resource

## Contract and ownership

`almasi.Resource` owns independently cancellable subscriptions. Every
`resource.subscribe(callback)` registers one callable and returns a distinct
opaque registration ID. `resource.unsubscribe(subscription_id)` cancels
that registration; cancellation is idempotent. There is no
identifier scope on a listener. `resource.is_subscribed()` reports whether
external observation is needed.

`resource.update(changed=None, subscription_id=None)` delivers the producer's change notification to
live subscribers in registration order, or to one registration when its ID is supplied. Notifications do not consume content.
Callbacks run synchronously in the producer's execution context. A canceled
listener is skipped if it has not started; cancellation does not wait for a
running callback. Direct callback exceptions propagate, while externally
observed resources log callback failures and deliver to the other listeners.

An external producer observes resource identity, not subscriptions. Resource
calls its optional observation callable when registration changes; the
producer reconciles the resource's current subscription state under its
existing source lock. No new worker or lock belongs to Resource. Inherited
filesystem and computed resources supply their source's observation callable.

## Filesystem specialization

FilesystemResource provides carrier identity in its supplying and effective
namespaces. File.read() delegates to its memoized format loader, including
legitimate None values. Directory.read() returns its namespace; passing an
exact filename resolves that child File and reads its content. Namespace
resolution uses read() for both types; Directory has no separate load method.

The canonical Almasi Filesystem service observes all resources, including
those belonging to forks. Each resource retains its effective namespace for
visibility and inherited override resolution, independently of the observer.

Filesystem owns watcher roots, effective file membership and its observation
context. File and Directory inherit the same subscription implementation from
FilesystemResource. Every registration receives its own initial mapping
of the currently observed effective files to `created` (including an empty mapping), and subsequent
changes through the same Resource.update operation. A File uses the key `'.'`;
a Directory uses relative file names with forward slashes. Notifications
describe effective file membership: a newly visible file is created, a missing
file is deleted, and a changed or replaced source is modified. Directories
themselves are not file entries.

Callback failures are logged for both initial and later notifications and do not
cancel registrations. The service replaces root-specific dispatch threads with one observation
event loop, using watchfiles.awatch to observe physical roots. All source
notifications, including deferred deployment publication, run in that context.
The synchronous subscribe API waits for registration, not the completion of
its initial callback. Cancellation remains idempotent. Generic non-filesystem
Resource subscriptions retain their existing producer-context behavior.

Existing watchers are shared by physical root and released when no resource
needs them. The service invalidates caches before notifying. A source callback
must not block the observation loop. Native watchfiles startup and overflow
still do not provide an atomic gap-free snapshot guarantee.

Example:

~~~python
import almasi

resource = almasi.File(almasi, '/tmp/example.txt', 'almasi.example')
subscription_id = resource.subscribe(print)
resource.unsubscribe(subscription_id)
~~~

## Writable values

`almasi.resources.Writable(value=None)` stores an in-memory value. `read()`
returns it without consuming it; `write(value)` replaces it and calls
`update()`, including when the new value equals the old one. Subscribers
use the inherited Resource contract. The owner decides which consumers may
write; the resource itself does not enforce authorization.

## Streams

`almasi.resources.Stream(max_bytes=None)` is a concrete byte resource backed
by an automatically removed temporary file. It does not interpret the bytes.
It inherits the subscription contract and provides:

- `write(data: bytes) -> None`: append bytes and notify after they are readable.
  Empty writes do not notify. Writes after close raise ValueError.
- `read(position=None, length=None) -> bytes`: read a finite available range
  without consuming it or blocking for future bytes. Positions and lengths
  are non-negative integers or None, not booleans. Omitted position is zero;
  omitted length means the available end. Reads at or beyond the end return
  empty bytes. Consumers own their own absolute cursors.
- `start_position` and `end_position`: inclusive earliest retained and
  exclusive latest absolute byte positions. These are individual observations,
  not a joint atomic snapshot.
- `close() -> None`: finish input and notify once. Existing bytes remain
  readable; repeated close is harmless. `closed` distinguishes end of input
  from temporarily absent bytes. The backing file is released automatically
  when the stream is released, not on close.

By default the entire history is retained on disk until release. For an
indefinite source, pass a positive integer `max_bytes` to bound disk usage.
The file reuses its byte locations circularly; absolute positions never wrap.
Reading an expired position raises ValueError, including omitted position
after byte zero has expired. A consumer can recover by selecting the current
start position. Binary media consumers must handle codec/frame boundaries
themselves. A read and a write are serialized at the storage boundary; the
file cursor is private and never acts as a subscriber cursor. Callbacks run
outside that storage lock; they are change hints, not a per-write event log.
As with other directly updated Resources, callback exceptions propagate to
the producer after the bytes or closure have been published.

Example:

~~~python
import almasi

stream = almasi.resources.Stream(max_bytes=1024 * 1024)
subscription_id = stream.subscribe(print)

stream.write(b'hello')
assert stream.read(0, 5) == b'hello'
stream.close()
assert stream.closed
stream.unsubscribe(subscription_id)
~~~

## Logs

`almasi.resources.Log(max_bytes=None)` specializes Stream without changing
its byte-oriented reads, writes, retention or subscriptions. Each nonempty
write adds one timestamp and exclusive byte-end position to a second temporary
file. A binary search locates the first selected entry in O(log N) index
reads; the selected data is read once. A bounded stream also bounds the index
to at most one 16-byte record per retained byte. No reader state is stored.

- `read(position=None, length=None)` returns bytes exactly as for Stream.
- `read(since=None)` returns all retained timestamped entries. Pass a finite
  Unix timestamp to select entries at or after that time (inclusive).
  Byte and timestamp coordinates cannot be combined.
- The result is `{'log': [{'timestamp': float, 'text': str}, ...],
  'last_timestamp': float | None}`. With no matching entries, last_timestamp
  is the supplied since (or None). Pass it as since on the next read; equal
  timestamps can repeat intentionally. Log decodes each entry as UTF-8 with
  replacement for invalid or split sequences. Ordinary byte reads preserve
  the original data without decoding.
- Timestamps use the producer's capture time in Unix seconds, not the time
  the child generated a message. Each write is one entry, not necessarily a
  complete line or UTF-8 character. Timestamps are clamped to the preceding
  entry's timestamp if the clock moves backward within this Log.
- If bounded retention expires bytes, timestamp reads return only retained
  entries, including a partial first entry when applicable. Byte reads keep
  the ordinary expired-position error contract.
- Both temporary files are released with the resource. Neither survives the
  owning process's exit. A replacement Log does not inherit its history.
  Writes and time reads share the Stream lock; notifications run after index
  publication. Disk I/O failures propagate; temporary storage is not durable
  or crash-transactional.

Example:

~~~python
import almasi

log = almasi.resources.Log()
log.write(b'hello\\n')
result = log.read(since=None)
assert result['log'][0]['text'] == 'hello\\n'
log.write(b'next\\n')
new = log.read(since=result['last_timestamp'])
assert new['log'][-1]['text'] == 'next\\n'
~~~

## Verification

Native resource, stream and filesystem tests cover separate handles, source
isolation, cancellation, watcher lifetime, inherited overrides, range
validation and cache invalidation. O owns its dependency-index tests.
