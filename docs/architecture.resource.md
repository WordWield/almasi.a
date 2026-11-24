# Architecture: generic Resource and filesystem specialization

**Status:** implemented by the corresponding Almasi resource PR; verify the CI and dependent O/Web integrations before declaring the cross-repository migration complete.

## Common contract

`a.Resource(a.Module)` provides a single shared Module ancestry for all
resource specializations, including filesystem and computed resources. It
remains source-independent and defines `read(position=None, length=None)` and
`subscribe(callback)`, each raising `NotImplementedError` until implemented
by a concrete resource. It does not own caching, a filesystem path, an O object
ID, subscription indexes or a notification transport.

Observation ownership remains in `a.Subscribable`: it registers and indexes
`a.Subscription` handles, selects recipients through the concrete source's
`_matches_generator` implementation, dispatches callbacks and handles
`update()` / `cancel()`. A Resource delegates observation to its
appropriate producer; the resource itself is not another subscription registry.

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
  `Directory.read(name)` retains the historical validated file lookup and
  plugin load behavior. Existing `load()`, `write()`, `mkdir()`, `copy()`,
  `link()` and namespace access contracts remain available.
- The existing `a.services.Filesystem(a.Subscribable)` watcher indexes only
  `FilesystemResource` instances; it does not accept unrelated Resource
  specializations. It continues to observe effective inherited sources,
  invalidate cache before notifying, and emit file status dictionaries with
  `created` / `modified` / `deleted` entries.

The generic base does **not** mandate a cache. Files continue to use the
existing plugin/module cache; computed resources in O may store their own value.

## Verification and compatibility

`root/tests/test_resource_subscriptions.py` covers the hierarchy, abstract
contract, uniform `read()`, existing `Directory.read(name)`, source-specific
registration and existing watcher notification/inheritance/cleanup behaviors.
Other filesystem, plugin, fork and reload tests must remain green.

This document covers Almasi only. O's `ComputedResource` implementation and
Web's MCP resource subscriptions belong to their respective repositories.

## Stream specialization

`almasi.StreamResource(almasi.Resource)` is a source-independent byte-stream
base. A concrete subclass implements `_read(position, length)` and
`subscribe(callback)` using its source. The source owns storage, retained history,
and observation. The base does not allocate a buffer or track subscriber cursors.

`read(position=None, length=None)` returns finite bytes available at the requested
absolute zero-based byte position. Omitted position means zero; omitted length
means through the currently available end. Both coordinates must be non-negative
integers (not booleans) or None; invalid coordinates raise ValueError. Length zero
requests no bytes. The source returns fewer bytes at the current end and reports
unavailable retained history rather than silently shifting the starting position.
Each consumer owns its next position, calculated as the requested position plus
the number of bytes received. Reads do not consume shared state. The source
implements change notifications using the existing subscription contract.

For example, a concrete stream resource read at position 100 with length 50
returns at most bytes 100 through 149. Ordinary non-stream resources retain
whole-value reads; range support is not implied for them.
