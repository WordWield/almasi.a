# Architecture: Subscribable — shared change subscriptions

**Status:** Shared Subscribable and filesystem resource subscriptions implemented.
O and Web integrate their own source-specific subscriptions separately.

## Intent

Almasi provides one reusable mechanism for registering interest in changes to
identified entities. A source supplies invalidations; consumers subscribe to a
set of identifiers and decide whether to read fresh state.

**One registration mechanism. Different sources of change.**

The subscription mechanism belongs to Almasi itself. It has no knowledge of
applications, network protocols, UI frameworks, external consumers, or ontology
semantics.

## Classes and ownership

```text
a.Singleton
    └── a.Subscribable
            └── a.services.Filesystem

a.Subscription

a.Resource
    ├── a.File
    └── a.Directory
```

- `Subscribable` extends `a.Singleton`, retaining Almasi's existing service
  singleton ownership within the relevant library/fork scope.
- Each concrete `Subscribable` service holds its own active subscriptions and
  receives changes from its own producer.
- `Subscription` owns one registration: its identifier set, callback and
  cancellation/update state. It is a runtime object, not a service.
- `Resource` defines the common read and subscription contract and owns
  direct registrations. `FilesystemResource` holds filesystem identity;
  File and Directory inherit it separately.
- `Filesystem` is the Almasi service that receives filesystem change events,
  resolves their effective resource identities and dispatches notifications.
- `FilesystemResource.subscribe(callback)` delegates to Filesystem instead
  of using the direct registration set. There is no duplicate registry or
  background worker on filesystem resources.

A concrete service is the natural owner of exactly one logical subscription
dispatcher. That does **not** imply exactly one OS watcher: the Filesystem
service may need watchers for several physical directory roots.

## Public contract

```python
# Proposed APIs; not yet available in the current runtime.
subscription = subscribable.subscribe({identifier_a, identifier_b}, callback)
subscription.update({identifier_c})
subscription.cancel()

resource_subscription = resource.subscribe(callback)
resource_subscription.cancel()
```

`subscribe(identifiers, callback)` creates a distinct subscription every
time, even when the same callback is used for another registration. The
identifier set is copied/snapshotted on registration and on update.
`update(identifiers)` atomically replaces the scope of this registration;
`cancel()` unregisters it and is idempotent.

Each source owns its change representation and matching semantics.
For O owner-ID invalidations, the matching rule is:

```python
matching = changed_identifiers & subscription.identifiers
```

O delivers matching owner IDs, including its full-invalidation sentinel.
Filesystem delivers resource paths and change statuses. The generic base
neither interprets these notifications nor imposes a common event format.

No content is transmitted by the subscription mechanism. Notifications are
invalidation hints: consumers reread only when necessary. A change may be
coalesced with others; subscriptions do not constitute an event history.

## Subscription API and execution rules

`a.Subscribable` is a service singleton that concrete producers extend.
Each source implements `_matches_generator(changed)` to yield
`(subscription, notification)` pairs. The base implementation raises
`NotImplementedError` when delivery is attempted without an override.

A concrete resource subscription can be used directly:

```python
import a

resource = a.File(a, '/tmp/example.txt', 'a.example')
subscription = resource.subscribe(lambda changes: print(changes))
subscription.cancel()
```

Filters accept `set`, `frozenset`, or `None` (all identifiers).
`subscribe(callback)` abbreviates `subscribe(None, callback)` for
sources supporting broad registration. Each call returns a distinct
`a.Subscription`. Updating a canceled handle raises `RuntimeError`;
cancellation is idempotent.

Internal producers call `_dispatch(changed)` with their own change
representation. Matching snapshots are selected by the concrete source.
A scope update during delivery affects later batches; cancellation skips
callbacks not yet invoked. Callback bodies execute in the producer's
thread, outside the registration lock. Callback exceptions are logged
and do not halt other deliveries.

## Shared dispatch and distinct producers

`Subscribable` implements registration, scope replacement, cancellation and
callback delivery once. Each concrete source implements
`_matches_generator(changed)`, yielding `(subscription, notification)` pairs.
The source decides how to match and what to deliver. Producers remain responsible for determining *what*
changed and *when* it is safe to report it.

The generator loop, if a producer uses one, belongs to the producer/service
lifecycle, not to individual subscriptions. An asynchronous generator is a
natural adapter for an OS watcher; it is **not** a requirement that every
producer be converted to an async generator.

The dispatcher must not impose an additional queue, worker or network
transport on producers. An existing producer can deliver a batch from its
own worker after it has completed source-specific processing. This keeps
subscription matching behind the producer's write/commit hot path.

Filesystem yields resource-specific `{path: change}` dictionaries from
`_matches_generator(changed)`. Generic `Subscribable._dispatch(changed)`
checks active subscriptions, invokes callbacks and isolates failures.
Each filesystem batch keeps its own event details, including nested
and concurrent notifications; no `ContextVar` or shared event state is used.

The dispatch implementation must support:

- Subscription registration/update/cancellation while delivery is underway,
  without corrupting iteration or delivering a partially updated scope.
- A defined locking/snapshot policy for concurrent producers and callbacks.
- Failure isolation: one subscriber exception does not prevent delivery to
  other subscribers.
- No callbacks while holding locks that would block reentrant subscription
  operations.
- Explicit ownership/lifetime of any long-running watcher.
- No global cross-library registry of subscription objects.

Callback execution context is a producer-level contract. A generic
`Subscribable` must not silently promise callbacks on an asyncio loop or
on the caller's thread.

## Filesystem source

`a.services.Filesystem(a.Subscribable)` uses an OS-backed
`watchfiles` watcher. This dependency belongs to the filesystem producer,
not to `Subscribable`.

Filesystem events are physical: added, modified and deleted paths. The
subscriber-facing identifiers represent the **effective Almasi resource**
after namespace resolution, including library inheritance and overrides.

`FilesystemResource.subscribe(callback)` subscribes to its logical resource:
- `File`: invalidation of that logical file, including replacement,
  deletion, recreation and changes of its effective inherited source.
- `Directory`: invalidations of the directory's logical subtree, including
  child additions/removals and modifications.

The Filesystem matcher uses set intersection on resource identities. It
must map physical paths to the relevant logical identifiers; for subtree
subscriptions it may include affected ancestor-directory identifiers in the
published set, or maintain an equivalent producer-specific index. Do **not**
reinterpret paths as opaque strings and assume intersection alone handles
tree membership.

A local override masks a parent-layer change when the effective resource is
unchanged. Removing the override can reveal an inherited file and must
invalidate the logical resource. Logical identities survive atomic
`os.replace`, deletion/recreation and changes to the supplying layer.
Watcher events alone do not establish that visible content changed.

The Filesystem service must invalidate affected Almasi carrier/content and
directory-child caches **before** calling subscribers. The current Almasi
cache rules only handle mutations through a receiving namespace face;
external filesystem edits and independent faces are not globally coherent
yet. Subscription support introduces that responsibility deliberately.

Watch only relevant configured roots, deduplicate equivalent observations,
and ignore temporary atomic-write artifacts that are not published resources.
A gap during watcher startup, an overflow or a restart requires revalidation
against current filesystem state. Exact normalization, alias and inheritance
mapping need tests before implementation.

## Lifecycle and identities

`Subscribable` is owned by its concrete service singleton, not by the
consumers. The service tracks active `Subscription` instances for dispatch;
each returned object is the handle the caller uses to cancel or update.
There is no separate application-wide list of Subscribable instances.

Filesystem watcher startup can be lazy and reference-counted by relevant
active subscriptions. A canceled file subscription does not stop a watcher
still needed by other subscribers.

Almasi forks and inherited library namespaces have distinct runtime
identity/cache scopes. A service singleton and its watcher state must be
bound to the appropriate owning library/fork, while avoiding duplicate OS
watchers for the same physical roots where safe. This is a design constraint,
not a claim that global shared cache invalidation already exists.

## Migration and verification

The shared subscription primitive and filesystem producer are implemented.
`Resource` is the common parent of `File` and `Directory`; both retain
`is_directory()`. The filesystem carrier contract is documented in
`almasi_invariants8.md`.

Implementation should proceed without inventing additional public API:

1. Introduce `Resource` and split `File` / `Directory` while preserving
   carrier identity, plugin resolution, loading and namespace behavior.
2. Implement `Subscription` and `Subscribable` with concurrency,
   reentrancy, scope update, cancellation and callback-failure tests.
3. Add the Filesystem producer and resource delegation; verify inherited
   overrides, nested directories, atomic replacement, external writes,
   cache invalidation and watcher recovery.
4. Verify singleton/fork isolation and absence of duplicated observers.
5. Verify no new work is imposed on unrelated reads or write hot paths.

**Invariant:** Everything necessary exists; all genuine subscription
commonality lives once in Almasi; each source retains its essential
change-detection and identity semantics. No consuming library is referenced
or required by this core architecture.

## Filesystem callback and event metadata

`Resource.subscribe(callback)` returns an `a.Subscription` handle.
File and directory subscriptions use the same registration and cancellation
mechanism; `Filesystem` alone owns the OS watcher.

Filesystem callbacks receive one dictionary per observed batch, mapping
relative resource paths to their final observed event:

```python
# Directory carrier, for example from a library namespace.
subscription = directory.subscribe(lambda resources: print(resources))
# {'static/app.js': 'modified', 'static/theme.css': 'created'}
subscription.cancel()
```

Event values are `'created'`, `'modified'`, or `'deleted'`.
Directory subscriptions observe descendants recursively, and removing a
directory does not terminate its subscription. An observed path can be
recreated later. Duplicate changes for one path within the same batch are
collapsed to one final observed event. There is no application-level batch
size limit.

The callback is an invalidation hint, not changed file contents. Consumers
may refetch when needed. In MCP, the consumer can publish the subscribed
resource URI with the dictionary in `_meta.resources`; transport delivery
and authorization remain outside Almasi.

Filesystem change detection is not a durable ordered change log: missed
or overflowed OS events may require a fresh resource read. A subscription
does not make content reads probe file timestamps or hashes.

## Indexed invalidation matching

The shared Subscribable maintains an inverted mapping from identifier to
interested Subscription handles. O's `_matches_generator()` uses that index
to find candidates and their matched owner IDs. Filesystem instead matches
resources and builds source-specific event dictionaries.

A complete immutable subscription view serves full invalidation, small
registrations and dense changes. The indexed route is used for sparse changes
on larger subscription sets. The choice affects execution cost, not observable
delivery behavior. Callback errors remain isolated and callbacks run outside
the registration lock. Filters are snapshotted at dispatch start; cancellation
remains nonblocking and suppresses callbacks not yet selected for invocation.

The index and immutable view are derived registration state, never independent
subscription authorities. Both are maintained by the same Subscribable.
