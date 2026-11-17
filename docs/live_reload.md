# Live Python module reload

Almasi can replace a source-backed `a.Module` or `a.Service` without
recreating objects already held by consumers.

## Supported entry points

A source-backed ordinary Module resolves to a class:

```python
Handler = library.handlers.Handler
handler = Handler()
handler.queue = ['pending']

NewHandler = Handler.__reload__()

assert handler.queue == ['pending']
assert type(handler) is NewHandler
assert library.handlers.Handler is NewHandler
```

A Service resolves to its singleton instance:

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

Service reload additionally transfers the singleton to the fresh class and
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
- Reload covers source classes using the ordinary Almasi `ModuleMeta`.
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

Declare a source-backed class with `a.ReloadableModule` or
`a.ReloadableService` to observe its original Python file:

```python
class Counter(a.ReloadableService):
	def read(self):
		return self.value
```

Both classes derive their shared behavior from the plain `a.Reloadable`
mixin, which does not inherit from `a.Module`. The Almasi Python plugin
installs one source subscription upon loading the class. A source change
marks it pending, without modifying live Python objects on the filesystem
watcher thread.

Call `a.Reloadable.apply_pending()` only at a **quiescent boundary**, after
all affected methods and suspended coroutines have completed. It reloads
pending source classes and returns the resulting classes. Service identity,
initialized state, and instance fields survive. Errors are propagated and
leave the change pending for a later attempt.

**Boundary:** This is opt-in change detection and deferred replacement, not
a request-draining scheduler. Hosts must explicitly arrange the safe boundary;
Almasi cannot infer one from a filesystem notification.

## Lifecycle callbacks

`Reloadable.__on_reload__(callback)` is a **class method** inherited by
`ReloadableModule` and `ReloadableService`. The callback accepts exactly one
argument: the existing, fully constructed instance. It fires once after the
first instance construction (after `__init__`), then after each successful
`apply_pending()` reload for every live instance of the changed class.
A subscription on a parent class also observes its subclasses. Callbacks
registered on a replaced source class survive that replacement.

```python
subscription = Controller.__on_reload__(mcp.register_controller)
# Load classes, then construct controller instances: callbacks fire.
# At a safe boundary, a.Reloadable.apply_pending() fires callbacks again.
subscription.cancel()
```

The returned `a.Subscription` supports `cancel()`. Registration does not
replay instances already created; attach the listener before constructing them.
Service callbacks run after construction, **not** after the separately called
`initialize()`. Callback exceptions are logged without rolling back a code
replacement that has already succeeded. Calling `__reload__()` directly
continues to bypass lifecycle notification; use `apply_pending()` for these
events.
