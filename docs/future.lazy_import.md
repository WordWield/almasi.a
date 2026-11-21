# Future: Lazy Import of Almasi Libraries

**Status:** Future concept. Not implemented. Not part of the current MCP extraction.

## Intent

An Almasi application should be able to use an Almasi library without separately installing every Almasi distribution in advance.

```python
from almasi import mcp, web, o

class Counter(mcp.Controller):

	@mcp.resource
	async def count(self):
		return 42
```

The `almasi` namespace identifies the library family. Thus `from almasi import mcp` refers to the Almasi MCP library, while an independently installed official MCP SDK remains available as `import mcp`. The libraries must not compete for the same top-level Python import name.

## Proposed resolution

When an Almasi library is requested:

1. **Resolve locally.** Reuse the library if it is already available in Almasi's local library space.
2. **Discover if missing.** Consult an Almasi library hub that maps a qualified library identity (such as `almasi.mcp`) to its trusted source repository.
3. **Acquire on demand.** Fetch the missing library from the registered source (initially, a GitHub repository) into the local Almasi library space.
4. **Prepare dependencies.** Make the library and any required third-party dependencies available through a defined installation mechanism.
5. **Load normally.** Complete the requested import through Almasi's library resolution mechanism.
6. **Reuse thereafter.** A subsequent import uses the local installation; it does not repeat acquisition.

The hub and lazy import are two parts of the **same library-resolution responsibility**: the hub identifies the source; resolution obtains a missing library only when it is needed.

## Architecture boundaries

- The existing Almasi filesystem/library resolver remains the source of library identity and ownership. Do not build a competing library registry or a parallel component loader.
- The location of the shared local library directory is not decided. Physical storage layout must not dictate Python's public namespace.
- Cloning a repository is **not** sufficient by itself to make its code importable: loading and external dependency installation must have explicit contracts.
- This concept does **not** imply automatic isolation of incompatible third-party dependency versions or conflicting `sys.modules` entries.
- `from almasi import mcp` is the desired developer-facing form. Supporting `import almasi.mcp` may require additional Python import-finder integration; it is not yet a guaranteed contract.
- Library acquisition happens only for recognized, trusted library identities. Source authentication, dependency integrity, permissions, and unexpected code execution require an explicit policy.
- Concurrent first imports, partial installs, rollback, offline behavior, and version/revision pinning must be defined before implementation.
- **Updates are separate from imports.** An ordinary import must not silently replace a locally available version.

## Out of scope for current development

This is a **future** capability. It does not change the existing Almasi installation model, the current MCP library extraction, or the official MCP SDK. No lazy installation, Git clone on import, automatic updates, or new import hook is being implemented by this document.

## Guiding principle

**A library is identified by what it is, not by whether its files have already been installed.**

Intent determines necessity: resolve what is needed, acquire only what is missing, and leave already available libraries undisturbed.
