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

`StreamResource` inherits subscriptions and implements range validation for
`read(position=None, length=None)`. A concrete source implements
`_read(position, length)` and calls `self.update()` after making bytes
available. Positions and lengths are non-negative integers or None, not
booleans. Omitted position is zero; omitted length means the available end.
A zero length requests no bytes. Consumers own their cursors; reads never
consume shared state. The source owns retained history and storage.

## Verification

Native resource, stream and filesystem tests cover separate handles, source
isolation, cancellation, watcher lifetime, inherited overrides, range
validation and cache invalidation. O owns its dependency-index tests.
