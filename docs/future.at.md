# Future: positional resource reads with `at`

**Status:** agreed architectural direction, not implemented. This document records the intended contract and the verified MCP SDK integration point.

## Intent

Allow multiple consumers to read different portions of the same stream without creating different resource identities or subscriptions. Keep reading source-independent and preserve ordinary resource behavior.

## Contract

```python
resource.read(at=None)
```

- `at=None` preserves ordinary reading.
- Every concrete `Resource.read()` accepts optional `at`. Ordinary resources ignore it; sources with positional reading interpret it.
- The consumer owns its reading position. `Subscription` remains an independent notification/cancellation handle, not a reader or cursor.
- Resource URI and subscription identity do **not** include `at`.
- The source owns data availability and retention/replay policy. The resource does not gain a universal persistence obligation.

The allowed position representation, chunk bound, next-position information, and missing-history behavior still require a concrete stream contract. Do not assume unlimited history or an unbounded read response.

## MCP wire request

Keep `at` beside `uri` in `resources/read.params`, **not** in the URI or `_meta`:

```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "method": "resources/read",
  "params": {
    "uri": "almasi://process/stdout",
    "at": 1000
  }
}
```

A standard `resources/read` without `at` must continue to work. The extra field is an **Almasi MCP extension**; external MCP clients are not required to emit it. The URI continues to determine the resource and shared subscription.

## Adapt the official Python MCP SDK without forking it

**Verified in SDK source:** `mcp_types.ReadResourceRequestParams` declares `uri`, not `at`. `MCPModel` has no `extra='allow'` setting; Pydantic therefore ignores unknown fields during validation. The low-level `Server.add_request_handler(method, params_type, handler)` is a supported registration point and replaces an existing handler for the method.

**Intended minimal adaptation in `almasi.mcp`:**

1. Define an Almasi-specific subclass of `ReadResourceRequestParams` with `at` optional (initially integer or `None`, pending the final position contract). Retain the original `uri` and SDK metadata fields.
2. After the `MCPServer` superclass initializes its low-level server, register `resources/read` with this extended params type and the **existing** `_handle_read_resource` handler. Reuse the SDK's complete resource dispatch/response conversion, rather than duplicating it or intercepting raw JSON.
3. SDK validation now retains `at`. Its `_handle_read_resource` constructs `Context(..., input_params=params, ...)`, so the Almasi resource callback can obtain `at` via `ctx.input_params.at` (verify the public context property against the installed SDK version).
4. Update `almasi.mcp/root/mcp_server.py` `McpServer._read_resource()`: resolve by the **unchanged** `uri`, then invoke `resource.read(at=at)` for Almasi resources and keep the existing serialization. Plain values do not acquire a reading cursor.

This is a targeted request-schema extension within the SDK's registration mechanism, **not** an SDK fork, a new MCP tool, or a URI rewrite. The SDK-specific registration must be tested against the dependency version installed by Almasi MCP.

## Almasi and Web integration

- In `almasi/lib/resource.py`, declare `read(at=None)` as the common contract. Update concrete overrides: `FilesystemResource` (including `Directory`, whose redundant `read(name)` override was removed), `o.ComputedResource`, and `web.WritableResource`. Ordinary values ignore `at`; only position-aware implementations use it.
- Preserve the existing `subscribe(callback)` contract, callback notification semantics, resource identity and source-owned registration lifetimes.
- Almasi Web's MCP client must send `params.at` on positional read requests; do not assume the stock SDK client method preserves an unrecognized field.
- Browser `Resources.js` currently caches one value and automatically refreshes after invalidation per URI. Before using it for streams, define how independent consumer reads avoid sharing one mutable cursor or overwriting one another's results. Keep a shared URI subscription if possible; do not treat `at` as a cache identity.
- No controller should need to interpret `at` merely to identify a resource. Position is a read concern, not an argument of the controller's resource factory.

## Verification before implementation is considered complete

1. Send a raw `resources/read` request with `uri` and `at`; assert the callback receives `at` after SDK validation.
2. Send the ordinary request containing only `uri`; assert it uses `at=None` and returns the prior value.
3. Confirm two positional reads with different `at` values resolve to the same resource URI and do not create additional subscriptions.
4. Check File/Directory, O computed and Web writable resources for signature compatibility, including ordinary and keyword `at` calls.
5. Verify MCP response serialization, browser independent reader positions, and subscription cleanup.

**Invariant:** One resource identity, independent listeners, one read contract; the optional reading position belongs to an individual read request, never to the resource URI.
