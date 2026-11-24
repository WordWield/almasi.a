# Architecture: Resource

## Contract and ownership

`almasi.Resource` owns independently cancellable subscriptions. Every
`resource.subscribe(callback)` registers one callable and returns a distinct
opaque registration ID. `resource.unsubscribe(subscription_id)` cancels
that registration; cancellation is idempotent. There is no
identifier scope on a listener. `resource.is_subscribed()` reports whether
external observation is needed.

`resource.update(changed=None)` delivers the producer's change notification to
live subscribers in registration order. Notifications do not consume content.
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

Filesystem owns watcher roots and effective paths. It observes a resource
once regardless of listener count, invalidates file and namespace caches before
calling resource.update({path: status}), and releases unused OS watchers.
Inherited overrides and fork-local resource identity remain unchanged.
A file observes its logical identity across replacement, removal, recreation
and changes of its supplying library layer. A directory observes its subtree.
Hidden parent changes do not invalidate a local override; removing that
override can reveal an inherited file. Notifications are coalescible hints,
not an event history. OS watchers do not by themselves establish global
cache freshness, nor guarantee gap-free delivery across watcher startup,
overflow or restart.

Example:

~~~python
import almasi

resource = almasi.File(almasi, '/tmp/example.txt', 'almasi.example')
subscription_id = resource.subscribe(print)
resource.unsubscribe(subscription_id)
~~~

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

## Verification

Native resource, stream and filesystem tests cover separate handles, source
isolation, cancellation, watcher lifetime, inherited overrides, range
validation and cache invalidation. O owns its dependency-index tests.
