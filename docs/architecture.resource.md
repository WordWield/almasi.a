# Architecture: generic Resource and filesystem specialization

**Status:** implemented by the corresponding Almasi resource PR; verify the CI and dependent O/Web integrations before declaring the cross-repository migration complete.

## Common contract

`a.Resource(a.Module)` provides a single shared Module ancestry for all
resource specializations, including filesystem and computed resources. It
remains source-independent. Its `read(position=None, length=None)` raises
`NotImplementedError` until implemented by a concrete resource.
Its default `subscribe(callback)` registers a callable on that resource and
returns a distinct cancellable `a.Subscription` handle. The resource creates
its registration set only when first subscribed. A concrete producer calls
`self._dispatch(changed)` after publishing a change. Callbacks receive the
producer's notification (normally None), synchronously; callback exceptions
propagate. Canceling a handle is idempotent. Direct subscriptions have no
identifier scope to update.

Indexed producers such as Filesystem and O Sync retain their existing
`a.Subscribable` registries and override `subscribe(callback)` to delegate
directly. Their resources do not create a second subscription registry.
No new lock, worker, cache or notification transport is introduced.

## Filesystem specialization

`a.FilesystemResource(a.Resource)` owns the existing filesystem carrier
identity: canonical real path, library/source, logical route, namespace face and
`get_path()`, `get_route()`, `get_lib()` and `get_name()`. It delegates
`subscribe(callback)` to its effective library's `a.services.Filesystem`.

`File(FilesystemResource)` and `Directory(FilesystemResource)` retain their
distinct behavior, plugins and namespace resolution.

- `File.read()` reuses `File.load()` and its existing memoization;
  `None` is still a valid cached file result.
- `Directory.read()` returns the directory namespace itself.
  It inherits the same read implementation as File. Existing `load()`,
  `write()`, `mkdir()`, `copy()`, `link()` and namespace access remain available.
- The existing `a.services.Filesystem(a.Subscribable)` watcher indexes only
  `FilesystemResource` instances; it does not accept unrelated Resource
  specializations. It continues to observe effective inherited sources,
  invalidate cache before notifying, and emit file status dictionaries with
  `created` / `modified` / `deleted` entries.

The generic base does **not** mandate a cache. Files continue to use the
existing plugin/module cache; computed resources in O may store their own value.

## Verification and compatibility

`root/tests/test_resource_subscriptions.py` covers the hierarchy, abstract
contract, uniform `read()`, direct subscription delivery and source-specific
registration and existing watcher notification/inheritance/cleanup behaviors.
Other filesystem, plugin, fork and reload tests must remain green.

This document covers Almasi only. O's `ComputedResource` implementation and
Web's MCP resource subscriptions belong to their respective repositories.

## Stream specialization

`almasi.StreamResource(almasi.Resource)` is a source-independent byte-stream
base. A concrete subclass implements `_read(position, length)` using its source
and inherits direct subscriptions from Resource. After making new bytes
available, the producer calls `self._dispatch(None)`. The source owns storage
and retained history. The base does not allocate a buffer or track subscriber cursors.

`read(position=None, length=None)` returns finite bytes available at the requested
absolute zero-based byte position. Omitted position means zero; omitted length
means through the currently available end. Both coordinates must be non-negative
integers (not booleans) or None; invalid coordinates raise ValueError. Length zero
requests no bytes. The source returns fewer bytes at the current end and reports
unavailable retained history rather than silently shifting the starting position.
Each consumer owns its next position, calculated as the requested position plus
the number of bytes received. Reads do not consume shared state.

For example, a concrete stream resource read at position 100 with length 50
returns at most bytes 100 through 149. Ordinary non-stream resources retain
whole-value reads; range support is not implied for them.
