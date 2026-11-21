# Future: Almasi Run — one entry point for a living application

## Intent

Start an entire personal Almasi environment with one command, without manually starting repositories and processes in a particular order.

**Grow your app.** A person owns an application that can evolve independently, discover existing capabilities, and acquire new ones. Applications are personal by default; common capabilities are reusable.

This document captures an architectural direction, **not an implemented Run service or an approved detailed specification**.

## Fundamental contract

**Run makes required capabilities available and keeps their processes running.**

A user invokes `almasi.run` (exact CLI syntax to be defined). Run discovers the required repositories, prepares their execution environments, brings up the necessary processes, makes the application reachable, and opens the browser in an interactive local session.

The user should not need to know the process graph, manually provision dependencies, or coordinate startup order.

Run manages the existence and execution of processes. It does **not** mediate ordinary application data operations.

## Responsibility boundaries

| Owner | Responsibility |
|---|---|
| `almasi.run` | Discover, acquire, prepare, launch, supervise, stop, and observe required capabilities; expose management and discovery via MCP |
| `almasi.o` | Object identity, types, persistent state, transactions, and coherence across participating processes |
| `almasi.web` | Browser presentation, transport, authorized projections, and live UI updates |
| App | Application meaning, user experience, behavior, and required capabilities |
| Source | A reusable capability and its execution semantics |
| Agent / generation service | Produce or modify missing functionality when discovery cannot satisfy the intent |

The App's runnable contract must be usable by Run without Run knowing its internal business logic. A single *user-facing* launch command does not require reimplementing the App's internal entry point.

## Capability discovery and reuse

1. Resolve the requested App or capability by name and declared meaning.
2. Check whether an appropriate capability is already running or installed.
3. Discover an existing implementation in configured repositories, including GitHub.
4. Reuse it if it satisfies the request; otherwise acquire and start it.
5. Only when no suitable implementation exists, offer or initiate generation through the appropriate agent, subject to verification and permissions.

**Do not generate a second `weather` merely because the first one has not yet been discovered.**

Discovery should use an explicit, inspectable capability contract. A GitHub repository name alone does not prove it is trusted, compatible, runnable, or suitable.

## Execution and lifecycle

Run is the entry point for the environment, not a central server through which every request passes.

- Prepare runnable environments and isolated containers as needed, reusing existing container facilities rather than inventing them.
- Resolve and start dependencies in a valid order.
- Recognize already-running instances and avoid duplicate launches.
- Track desired and observed process state; recover from failures and expose actionable status.
- Make required services reachable and open the browser when a local interactive session is requested.
- Start with one ordinary host; support additional hosts only when justified by actual requirements.
- Treat infrastructure providers, including cloud vendors, as replaceable resources rather than architectural foundations.

A single machine may host several personal environments. Each has its own data and authority boundary; multiple applications may share capabilities only where explicitly permitted. A dedicated physical server per person is not required.

## Shared O: reuse the existing multiprocess implementation

**There is no need to create a central O server.** On a single host, participating processes can use the existing O implementation:

- LMDB stores committed object state.
- O Sync publishes invalidations following commits.
- O Transport relays invalidation notifications via a host-local Unix domain socket.
- Processes invalidate local caches and reread current data through O.

Run selects or provisions the ontology location and grants appropriate processes access. Each participating process initializes O using the existing public contract, conceptually `o.start(path=<shared absolute path>, multiprocess=True)`.

For containers, the actual LMDB location and transport socket directory must be available with consistent filesystem paths and permissions. **Shared LMDB access is a broad data permission**; untrusted capabilities must not receive unrestricted storage access. Isolation and authorization require a deliberate trust design.

O's current transport is host-local; cross-host shared state is **not** solved by Run's process scheduler. Do not claim network-distributed O consistency without a separately verified need and design.

## Management and MCP

Run exposes the same management capabilities to Python callers and MCP clients, without parallel implementations:

- Find and inspect available capabilities.
- Start and stop instances.
- Inspect status and failures.
- Read process logs and discover their provenance.

Actual Python method names and MCP resource identifiers are **not yet defined**. MCP is a standard interface to Run's existing capabilities, not a separate control plane with separate behavior.

### Logs as resources

Each supervised process has a log resource discoverable through Run. Authorized clients can read it and subscribe to changes using MCP's native resource subscription facilities.

- Preserve origin (process, capability, instance) and ordering information.
- A subscription signals an update; an MCP client decides how and when to surface it to an LLM.
- Logging must avoid recording secrets **at the source**, rather than relying on post-hoc scrubbing.
- Retention, limits, access rights, and structured-vs-text representation remain open decisions.

No new agent-specific log subscription mechanism is required.

## Necessary symmetry

- **One user-facing entry point:** Run starts the environment; no terminal choreography.
- **One process lifecycle:** the same supervision model applies to App, Source, and Agent.
- **One object system:** O remains the owner of data and coherence, not Run.
- **One capability contract:** reusable implementations can be discovered and run without special-case wiring.
- **One management surface:** Python and MCP expose the same operations.
- **Isolation by default, collaboration by necessity:** personal applications can evolve separately and interact when authorized.

Run should never be forced into application-specific orchestration merely because a capability was added.

## First vertical experiment

1. Launch Run with an existing App on one host.
2. Run starts required processes, attaches them to a designated O, and opens the App in the browser.
3. Confirm that two participating processes observe committed O changes using the existing multiprocess implementation.
4. Read a process's logs through a Run MCP resource and subscribe to updates.
5. Add a second Source capability; verify that Run discovers and starts it **without changing Run's implementation**.
6. Stop or crash a supervised process; verify status and recovery behavior.

This validates the architecture before automatic code generation, cross-host placement, or sophisticated resource scheduling.

## Open questions

- What is the minimal runnable capability descriptor and stable identity?
- How are trusted repositories, versions, startup dependencies, and conflicts resolved?
- What is the exact boundary between Run and application selection or onboarding?
- How are O paths, filesystem permissions, credentials, and container isolation provisioned safely?
- Which conditions should trigger automatic generation, and who approves generated code?
- How are log read/subscription permissions, retention, and cursor semantics defined?
- How should one host handle several independent user environments?
- Which verified requirements, if any, justify placement across different hosts?

## Status

**Future architecture.** The shared O multiprocess storage/invalidation mechanism exists in `almasi.o`; a minimal Source/App request-response demonstration exists in `almasi.source` / `almasi.api`. A general `almasi.run` orchestrator and its MCP discovery/management interface have **not** been implemented or verified by this document.

The goal is to remove unnecessary infrastructure, not accumulate a new platform in its place.
