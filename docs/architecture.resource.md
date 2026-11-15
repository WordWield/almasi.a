# Architecture: generic Resource and filesystem specialization

**Status:** implemented by the corresponding Almasi resource PR; verify the CI and dependent O/Web integrations before declaring the cross-repository migration complete.

## Common contract

`a.Resource` is source-independent. It defines `read()` and
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
