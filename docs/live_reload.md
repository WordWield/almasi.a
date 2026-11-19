# Live Python module reload

Almasi can replace a source-backed `a.ReloadableModule` or `a.ReloadableService` without
recreating objects already held by consumers.

## Supported entry points

A source-backed ReloadableModule resolves to a class:

```python
Handler = library.handlers.Handler
handler = Handler()
handler.queue = ['pending']

NewHandler = Handler.__reload__()

assert handler.queue == ['pending']
assert type(handler) is NewHandler
assert library.handlers.Handler is NewHandler
```

A ReloadableService resolves to its singleton instance:

```python
service = library.services.Orders
service.requests = 7

assert service.__reload__() is service
assert library.services.Orders is service
assert service.requests == 7
```

Both entry points reload the Python source from disk, preserve the identities
and instance dictionaries of existing objects, publish the fresh class through
the filesystem namespace, and invalidate its cached file carrier. Repeated
reloads are supported. New code is compiled directly from source rather than
accepting a potentially stale bytecode cache.

ReloadableService reload additionally transfers the singleton to the fresh class and
refreshes the instance-owned initialization wrapper. An already initialized
service is **not** initialized again. Existing direct subclasses are rebased
on the fresh parent class so inherited methods and `super()` continue
resolving through the new parent.

Callbacks wrapped by `lib.function.Function` and stored by
`lib.events.Events` resolve methods on their current module instance.
This lets registered callbacks and `on`/`off` retain their identity
across code replacements.

## Requirements and boundaries

- Invoke reload only at a **quiescent execution boundary**, after active calls
  of the affected module or service have finished. Almasi does not yet
  pause new calls or wait for suspended coroutines; changing `__class__`
  while an old function executes `super()` can raise `TypeError`.
- Source classes must have the same direct Python bases and compatible
  instance memory layouts. Incompatible replacements raise an exception.
- Existing ordinary bound methods and function aliases captured outside
  `Function` retain their old function objects. Consumers that need new
  behavior must look up the method again or use `Function`.
- New required instance fields must be initialized explicitly. Reload
  preserves existing `self.__dict__` rather than invoking a new `__init__`
  or `initialize`.
- Class-level mutable state is not transferred to the new class. Store state
  that must survive reload on an instance, or in a persistent store.
- Reload covers source classes deriving from the Almasi `Reloadable` mixin.
  Ontology classes with their own metaclass, runtime-only classes and
  arbitrary Python modules have different lifecycle requirements.
- Fresh class bodies execute during staging. Their import-time side
  effects are not reversible by the reload mechanism.
- External changes (including `git pull`) are not watched automatically.
  A caller must detect the source change and invoke `__reload__()` at the
  appropriate safe boundary. No request-draining mechanism is included.

A syntax or class-contract failure leaves the published module and namespace
unchanged. When class reassignment fails, changed instances and direct
subclass bases are rolled back before the error propagates.

## Opt-in source observation

A source-backed class may derive from `a.ReloadableModule` or
`a.ReloadableService` to subscribe to changes to its own Python file:

```python
class Counter(a.ReloadableService):
	def read(self):
		return self.value
```

The loaded source class owns one `a.File` subscription. A successful reload
transfers that subscription to its replacement class, without a global registry
of observed source paths. When the source changes, it invokes the existing
`__reload__()` behavior, preserving live instances and state.
If replacement fails, the current published class remains in place and the
exception is logged.

**Concurrency limitation:** filesystem callbacks run on observer threads.
Reloading from a callback does not drain in-flight calls or suspended
coroutines. Applications requiring concurrent safety must arrange for affected
execution to be quiescent before a source update is applied. This implementation
does not provide such a barrier.

## Lifecycle callbacks

`Reloadable.__on_reload__(callback)` is a **class method**. Register a callback
once on a base class to receive all its newly constructed instances, and all
live instances of a source class after successful reload. Each callback
receives the instance, including for services with singleton identity.

```python
Controller.__on_reload__(mcp.register_controller)
# Construct controllers as files are discovered; registration is automatic.
# A successful source reload re-registers those same controller instances.
```

Each class has at most one callback. Calling `__on_reload__()` again replaces
that callback. Subclasses inherit it through ordinary Python attribute lookup
unless they install their own. A class-specific callback is retained across source
revisions. No listener registry or cancellation mechanism is needed.

For ordinary modules the initial notification occurs after `__init__`.
For services it happens when the singleton is first created, **before**
the separately invoked `initialize()`. Callback failures are logged and do
not undo a successful reload. Explicit calls to `__reload__()` do not emit
lifecycle notifications; notifications are driven by Reloadable's observation.
