# Architecture: Subscribable — shared change subscriptions

**Status:** Stage 1 implemented in the accompanying PR (shared subscription\nprimitives). Filesystem, Resource hierarchy and producer migrations remain\nplanned.

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
a.Service
    └── a.Subscribable
            └── a.services.Filesystem

a.Subscription

a.Resource
    ├── a.File
    └── a.Directory
```

- `Subscribable` extends `a.Service`, retaining Almasi's existing service
  singleton ownership within the relevant library/fork scope.
- Each concrete `Subscribable` service holds its own active subscriptions and
  receives changes from its own producer.
- `Subscription` owns one registration: its identifier set, callback and
  cancellation/update state. It is a runtime object, not a service.
- `Resource` is the common filesystem carrier identity. `File` and
  `Directory` extend it as distinct types. The proposed hierarchy supersedes
  the current `Directory(File)` relationship and `is_directory()` predicate.
- `Filesystem` is the Almasi service that receives filesystem change events,
  resolves their effective resource identities and dispatches notifications.
- `Resource.subscribe(callback)` delegates to the Filesystem service. It does
  not own a separate observer, registration registry or background worker.

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

The abstract change unit is a set of identifiers, not a changed value or
object snapshot. For an ordinary batch:

```python
matching = changed_identifiers & subscription.identifiers
```

A nonempty intersection triggers the callback with the matching identifiers.
An empty subscription set matches no ordinary changes. A special
full-invalidation signal may be supported by a concrete producer when its
contract requires it; it is not an ordinary identifier and cannot collide
with a legitimate identifier. The precise common representation of that
signal must be selected before implementation.

No content is transmitted by the subscription mechanism. Notifications are
invalidation hints: consumers reread only when necessary. A change may be
coalesced with others; subscriptions do not constitute an event history.

## Stage 1 API and execution rules\n\n`a.Subscribable` is itself a service singleton and can be instantiated\ndirectly for tests or extended by a concrete producer. It does not require\n`initialize()` because its registration storage is established by `__new__`.\nConcrete services retain their own optional explicit initializers.\n\n```python\nimport a\n\nsource = a.Subscribable()\n\n# An unfiltered subscription; callbacks run synchronously during delivery.\nsubscription = source.subscribe(lambda changed: print(changed))\nsubscription.update({12, 35})\nsubscription.cancel()\n```\n\nAccepted filters are `set`, `frozenset`, or `None` (all changes).\n`subscribe(callback)` abbreviates `subscribe(None, callback)`. Every call\nreturns a distinct `a.Subscription`; the same callback can be registered\nmore than once. `update()` on a canceled handle raises `RuntimeError`;\n`cancel()` is idempotent.\n\nInternal producers call `_dispatch(changed)` with a set, frozenset or\n`None`. The batch is snapshotted once. Filter changes made during delivery\napply to later batches, while cancellation suppresses not-yet-reserved\ncallbacks. A callback already selected for invocation may finish after\n`cancel()` returns. Callbacks run in the dispatching thread, without\nlocks held across their bodies. Exceptions are logged and do not halt\nother deliveries.\n\n## Shared dispatch and distinct producers

`Subscribable` implements registration, scope replacement, cancellation,
matching and dispatch once. It exposes an internal delivery operation to
concrete services. Producers remain responsible for determining *what*
changed and *when* it is safe to report it.

The generator loop, if a producer uses one, belongs to the producer/service
lifecycle, not to individual subscriptions. An asynchronous generator is a
natural adapter for an OS watcher; it is **not** a requirement that every
producer be converted to an async generator.

The dispatcher must not impose an additional queue, worker or network
transport on producers. An existing producer can deliver a batch from its
own worker after it has completed source-specific processing. This keeps
subscription matching behind the producer's write/commit hot path.

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

The proposed `a.services.Filesystem(a.Subscribable)` uses an OS-backed
watcher, with `watchfiles` as the candidate adapter. It is a dependency of
the filesystem implementation, not of `Subscribable`.

Filesystem events are physical: added, modified and deleted paths. The
subscriber-facing identifiers represent the **effective Almasi resource**
after namespace resolution, including library inheritance and overrides.

`Resource.subscribe(callback)` subscribes to its logical resource:
- `File`: invalidation of that logical file, including replacement,
  deletion, recreation and changes of its effective inherited source.
- `Directory`: invalidations of the directory's logical subtree, including
  child additions/removals and modifications.

The generic dispatcher still uses set intersection. The Filesystem producer
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

Only the shared subscription primitive is implemented by Stage 1. Today,
`Directory` extends `File`; file carriers provide `is_directory()`;
there is no Filesystem subscription service. The existing Almasi filesystem
contract is documented in `almasi_invariants8.md`.

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
