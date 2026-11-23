# Future: Almasi Hub — one entry point for a living application

## Intent

Start an entire personal Almasi environment with one command, without manually starting repositories and processes in a particular order.

**Grow your app.** A person owns an application that can evolve independently, discover existing capabilities, and acquire new ones. Applications are personal by default; common capabilities are reusable.

This document captures an architectural direction, **not an implemented Hub service or an approved detailed specification**.

## Why this architecture exists

Traditional software is usually built once for many users who must adapt to its fixed feature set. Almasi reverses that relationship: **the App belongs to the person and may evolve with that person**.

An App need not become a centralized, conventional multi-user SaaS product. Its owner can extend its behavior, data model, interface, and integrations independently, including with AI assistance. A change to one person's App does not require changing every other person's App.

This does **not** forbid collaboration or shared state. It separates two concerns:
- **Ownership and evolution:** a personal App and its ontology are independently governed.
- **Reuse and interaction:** implementations (Source, Agent, other libraries) can be shared, and distinct Apps can exchange permitted information when that is actually needed.

Multiple users may reside on one physical host, each with a logically separate environment. A person need not own dedicated hardware. No application-wide distributed state or mandatory global multi-tenant runtime is required merely because there are many users.

The wider ecosystem is effectively **a repository of repositories**: independently developed capabilities can be discovered, started, maintained, and reused without imposing a single monolithic application structure.

### Guiding proposition

> One user, an App that grows with them, shared reusable capabilities, and an execution environment that does not demand a DevOps department.

**"Grow your app"** is the working product expression, not a finalized trademark or market claim.


## Personal ownership and first contact with WordWield

The intended end-user experience begins with a person, not an infrastructure diagram:

1. A person comes to **WordWield** to grow a personal App.
2. WordWield asks what their GitHub organization should be called and guides them through connecting their GitHub account.
3. The person creates or selects an organization they control. Where GitHub does not expose organization creation to the authorized integration, WordWield guides them through GitHub's own creation flow instead of inventing credential workarounds.
4. The person authorizes a WordWield GitHub App installation with only the repository permissions required for the requested work. **WordWield does not collect or copy the person's SSH keys, personal access tokens, or unrelated secrets.** The installation is revocable.
5. That organization becomes the home for their own Almasi repositories: their App, and Source or Agent code that they create or intentionally customize.
6. WordWield invokes Hub to resolve and launch the required capabilities. The user can then interact with a living App and ask it to develop further.
7. New capabilities are reused when available; genuinely new or personalized implementations are committed to repositories belonging to the person.

The organization is a **configured location**, not an identity or code-level constant hardwired into Hub. It is a namespace and ownership boundary for source repositories, not the runtime owner of O data.

### What lives where

- **User's GitHub organization:** original or modified source code belonging to that person, plus its release artifacts.
- **WordWield's GitHub organization:** shared Almasi infrastructure libraries, common Source/Agent implementations, and other reusable code. Names and exact organization membership are deployment choices, not Hub dependencies.
- **Hub on the selected host:** live processes, execution environments, supervision, and discovery/management interfaces.
- **O on the selected host:** persistent object state, types, identities, and transactional changes for the environment. O is **not** the repository catalog and does not move to GitHub merely because the code is stored there.

A user does not need to fork every shared Source. Hub should reuse an existing compatible implementation directly, and a new repository is warranted only when the user needs an independently evolving implementation.

This is the ownership promise: **the user owns the source of their growing App, not merely an account on someone else's centralized application.**

## Fundamental contract

**Canonical name: `almasi.hub`.** The former working name was
`almasi.run`; the architecture now uses Hub consistently because the
component discovers, acquires, launches, supervises, and exposes capabilities
without owning their implementations or sitting on every request path.


**Hub makes required capabilities available and keeps their processes running.**

A user invokes `almasi.hub` (exact CLI syntax to be defined). Hub discovers the required repositories, prepares their execution environments, brings up the necessary processes, makes the application reachable, and opens the browser in an interactive local session.

The user should not need to know the process graph, manually provision dependencies, or coordinate startup order.

Hub manages the existence and execution of processes. It does **not** mediate ordinary application data operations.

## Responsibility boundaries

| Owner | Responsibility |
|---|---|
| `almasi.hub` | Discover, acquire, prepare, launch, supervise, stop, and observe required capabilities; expose management and discovery via MCP |
| `almasi.o` | Object identity, types, persistent state, transactions, and coherence across participating processes |
| `almasi.web` | Browser presentation, transport, authorized projections, and live UI updates |
| App | Application meaning, user experience, behavior, and required capabilities |
| Source | A reusable capability and its execution semantics |
| Agent / generation service | Produce or modify missing functionality when discovery cannot satisfy the intent |

The App's runnable contract must be usable by Hub without Hub knowing its internal business logic. A single *user-facing* launch command does not require reimplementing the App's internal entry point.

## Capability discovery and reuse

1. Resolve the requested App or capability by name and declared meaning.
2. Check whether an appropriate capability is already running or installed.
3. Discover an existing implementation in configured repositories, including GitHub.
4. Reuse it if it satisfies the request; otherwise acquire and start it.
5. Only when no suitable implementation exists, offer or initiate generation through the appropriate agent, subject to verification and permissions.

**Do not generate a second `weather` merely because the first one has not yet been discovered.**

Discovery should use an explicit, inspectable capability contract. A GitHub repository name alone does not prove it is trusted, compatible, runnable, or suitable.

## GitHub organization as the capability catalog

A configured **GitHub organization** is the natural entry point for finding repository-based capabilities. No separate custom registry database is required by the basic design.

Hub can resolve a requested capability through:

```text
Configured GitHub organization(s)
              |
       Repository names
              |
       Versioned releases
              |
     almasi.json release asset
              |
       Capability metadata
              |
  Resolve and launch implementation
```

Repository names and Almasi naming conventions provide **candidate discovery**, not proof that a capability exists. The release index supplies the structured evidence of which methods, inputs, outputs, and meanings that version exposes.

The organization is configurable, so independent developers or users can publish Almasi-compatible Sources without joining WordWield's organization. WordWield's organization can be a convenient initial/default catalog, but is not part of Hub's implementation.

### The code is the only source of truth

Descriptions must not become a second manually maintained model of an App or Source.

- Existing controller declarations, `@bus.base.Controller.method`, method names, signatures, type information, and docstrings are the authoritative basis for describing Python capabilities.
- A **deterministic generator** derives a machine-readable `almasi.json` index from those sources during publication. The schema and extraction rules remain to be designed.
- **GitHub Actions** should own automatic generation and publication on a release event. The index is published **as a release artifact beside the exact version** of the code, not treated as a manually edited project manifest.
- The index records enough immutable version/commit identity for Hub to obtain the matching code and reject incompatible or stale metadata.
- Hub reads this small release artifact to discover capabilities **without downloading or executing the full repository and without asking an LLM to interpret it at search time**.
- Hub fetches the full repository only after a suitable candidate has been selected and execution is actually required.

The generator should not need an LLM to extract ordinary static declarations. If a capability is defined dynamically and cannot be described by the agreed extraction contract, the release pipeline must either resolve it safely in an isolated build context or fail explicitly; it must not silently fabricate metadata.

**Generation happens during publication, not on each user's discovery request.** Automatic consistency comes from deriving the release index from the same commit, rather than trying to keep two independently edited descriptions synchronized.

A release asset is an **index/projection of source code**, not another source of truth. No general-purpose inference service is needed just to list existing methods.

### Repository resolution is not a trust grant

Finding a matching `almasi.json` does not authorize arbitrary code execution. Before running an implementation, the system must verify the selected version and apply the appropriate provenance, permission, compatibility, and isolation policy. Those policies are real requirements, not an excuse to insert an unnecessary registry layer.

GitHub Actions and release artifacts are the current publication convention; Hub should keep its capability contract distinct from the identity of the hosting provider.

## Source, App, and Hub are not competing entry points

An App remains a runnable unit with its own execution contract, while **Hub is the sole user-facing entry point for starting the entire environment**. These are compatible requirements: Hub invokes the ordinary App entry point instead of creating a second way for App code to initialize.

Source and Agent are likewise runnable capabilities; Hub treats their lifecycles uniformly. A Source should be thin: the reusable capability is separate from the mechanics that find, launch, and supervise it.

### Warm and cold resolution

- **Already running:** reuse an appropriate healthy instance with no unnecessary launch.
- **Installed but stopped:** start the existing implementation.
- **Available in a configured repository:** acquire and prepare a compatible version, then start.
- **Absent:** request generation by a suitable capability, followed by validation before execution.

MCP is for discovery and control, **not a compulsory hop in each ordinary Source call**. Once a process is running, consumers should use its existing interface and O without recurring discovery overhead.

Performance is an explicit ambition, not a measured result: warm resolution should be fast, cold acquisition and launch should be measured, and the design should avoid redundant workers and dependency starts.


## Execution and lifecycle

Hub is the entry point for the environment, not a central server through which every request passes.

- Prepare runnable environments and isolated containers as needed, reusing existing container facilities rather than inventing them.
- Resolve and start dependencies in a valid order.
- Recognize already-running instances and avoid duplicate launches.
- Track desired and observed process state; recover from failures and expose actionable status.
- Make required services reachable and open the browser when a local interactive session is requested.
- Start with one ordinary host; support additional hosts only when justified by actual requirements.
- Treat infrastructure providers, including cloud vendors, as replaceable resources rather than architectural foundations.

A single machine may host several personal environments. Each has its own data and authority boundary; multiple applications may share capabilities only where explicitly permitted. A dedicated physical server per person is not required.

### The launch experience

For a local interactive environment, the intended experience is one command — conceptually `almasi.hub` — followed by a working application in the browser. The exact CLI and deployment mode remain open.

Hub brings up only what is required. The user does not manually start O, several Source processes, Web, workers, and the browser in sequence.

Conceptual flow:

```text
User intent / launch
        |
     Almasi Hub
        |
  Discover / reuse / acquire capabilities
        |
  Prepare environments and shared O location
        |
  Launch required App / Source / Agent processes
        |
  Supervise health, logs, and lifecycle
        |
  Expose Web and open browser (interactive mode)
```

This ordering does **not** imply a central O daemon. Individual processes initialize their O access as part of their startup. Hub owns their orchestration, not their object model.

### Desired state, observed state

Hub's minimal supervision model compares **what should be running** against **what is actually running**, and reconciles meaningful differences. Starting, observing, and restarting are aspects of one lifecycle model, not separate infrastructures.

When moving from one host to several is eventually justified, avoid duplicating this lifecycle model. Placement and recovery may become more complex, but the public concept of a required runnable capability should remain the same.

Hub does not promise magical fault tolerance: transient failures, persistent misconfiguration, crash loops, and unsafe updates require explicit policies and evidence before automatic actions are enabled.


## Shared O: reuse the existing multiprocess implementation

**There is no need to create a central O server.** On a single host, participating processes can use the existing O implementation:

- LMDB stores committed object state.
- O Sync publishes invalidations following commits.
- O Transport relays invalidation notifications via a host-local Unix domain socket.
- Processes invalidate local caches and reread current data through O.

Hub selects or provisions the ontology location and grants appropriate processes access. Each participating process initializes O using the existing public contract, conceptually `o.start(path=<shared absolute path>, multiprocess=True)`.

For containers, the actual LMDB location and transport socket directory must be available with consistent filesystem paths and permissions. **Shared LMDB access is a broad data permission**; untrusted capabilities must not receive unrestricted storage access. Isolation and authorization require a deliberate trust design.

O's current transport is host-local; cross-host shared state is **not** solved by Hub's process scheduler. Do not claim network-distributed O consistency without a separately verified need and design.

### What existing O implementation already gives us

The current `almasi.o` implementation contains host-local multiprocess coordination and has source-level tests. A concrete shared-path start signature exists in `root/services/ontology.py`. The original idea therefore needs **integration into Hub**, not a new O transport.

The current O transport is an invalidation relay, not a remote object API, transactional event log, authenticated network service, or cross-machine state replication. Claims about those features must be supported by separate implementation and tests.

An important risk remains: mounting an entire LMDB environment into an untrusted container grants broad storage access. Container isolation alone does not provide field-level authorization; sharing O must respect a clearly defined trust and permission boundary.


## Bus bootstrap and lazy capability access

Hub is the first locally available infrastructure capability, rather than a
Source that must itself be discovered through Hub. After Hub starts, its
management operations are exposed through the **same Almasi Bus and shared O
request bus** as Source methods, not a separate RPC implementation.

Conceptual Python interface (not yet implemented):

```python
bus.hub.load('google')
bus.google.search.web(query='...')
```

Resolving `bus.google` ensures that a suitable Source is acquired, started,
and ready **at attribute resolution time**, before invoking `.search.web()`.
Internally this uses the same Hub loading capability; no special discovery
network protocol should be introduced for Bus. Since the current
`bus.request()` immediately returns a persistent request node, the future
dotted Bus must explicitly wait for Hub's successful readiness result, and
surface installation or startup errors before routing Source calls.

Hub uses the shared O bus for its operations but does **not** intermediate
subsequent `bus.google.search.web(...)` business calls. Their requests
travel directly through O to the running Source. The exact dynamic Python
attribute mechanism, readiness and failure contracts, and concurrency
deduplication remain to be designed and tested.

## Management and MCP

Hub exposes the same management capabilities to Python callers and MCP clients, without parallel implementations:

- Find and inspect available capabilities.
- Start and stop instances.
- Inspect status and failures.
- Read process logs and discover their provenance.

Actual Python method names and MCP resource identifiers are **not yet defined**. MCP is a standard interface to Hub's existing capabilities, not a separate control plane with separate behavior.

### Logs as resources

Each supervised process has a log resource discoverable through Hub. Authorized clients can read it and subscribe to changes using MCP's native resource subscription facilities.

- Preserve origin (process, capability, instance) and ordering information.
- A subscription signals an update; an MCP client decides how and when to surface it to an LLM.
- Logging must avoid recording secrets **at the source**, rather than relying on post-hoc scrubbing.
- Retention, limits, access rights, and structured-vs-text representation remain open decisions.

No new agent-specific log subscription mechanism is required.

### MCP resources and operations

**The Source Bus has no Tool/Resource distinction.** Every callable Source
capability is declared with `@bus.base.Controller.method`; persistent
state and subscriptions belong to O. Hub uses this same Bus to implement
its management operations, not a separate set of MCP-typed controllers.

The MCP interface is an **adapter at Hub's external boundary**. It maps
operations to MCP Tools and O-backed readable or subscribable values (such
as process logs) to MCP Resources only where those protocol semantics are
appropriate. These are not new Source-side capability kinds or decorators.
The boundary must preserve real differences between invocation and state,
without duplicating implementation or the capability catalog.

The Python dotted interface and the MCP surface are **two presentations of the same underlying Hub capabilities**. The dotted names `hub.start`, `hub.status`, `hub.logs`, and `hub.stop` are conceptual examples only, not committed APIs.

Logs are naturally **MCP Resources** (and can use the protocol's resource subscription mechanisms). The start/stop/discovery operations should use the MCP semantics appropriate to their actions; not every operation is itself a Resource.

A Source does not need to implement a separate MCP server merely to be discoverable through Hub. Hub's catalog can expose installed and remote repository capabilities, while a Source's own application interface remains independent.

A subscription belongs to an MCP client. It does not guarantee that a language model is continuously running or automatically consuming each log line. No special Hub-to-LLM log streaming mechanism should be added unless a real requirement demands it.


## Necessary symmetry

- **One user-facing entry point:** Hub starts the environment; no terminal choreography.
- **One process lifecycle:** the same supervision model applies to App, Source, and Agent.
- **One object system:** O remains the owner of data and coherence, not Hub.
- **One capability contract:** reusable implementations can be discovered and run without special-case wiring.
- **One management surface:** Python and MCP expose the same operations.
- **Isolation by default, collaboration by necessity:** personal applications can evolve separately and interact when authorized.

Hub should never be forced into application-specific orchestration merely because a capability was added.

## Proposed commercial model and ecosystem effects

The working economic hypothesis is:

- **Capabilities and core software can be free/open**, including sharing reusable Sources and Agents.
- **Hosting and physical resources cost money.** Hub can eventually offer managed personal hosting while remaining independent of any particular vendor.
- **AI generation may cost money** where inference/verification uses paid compute; local generation may avoid a separate generation fee but still consumes resources.

The platform should make money from **providing real resources**, not from artificially restricting a person's capacity to extend their App.

One Source implementation may be reused many times without regenerating it for every owner. As the catalog grows, newly created Apps may gain useful abilities more cheaply. That is a plausible **network effect**, not yet a validated business result.

Open architecture, portable App data, and cloud independence preserve user autonomy. Hosting is optional: a standard Linux machine must be a viable starting point. The ambition is to eliminate **unnecessary manual DevOps work**, not to pretend security, operations, deployment, and incident recovery stop existing.


## First vertical experiment

1. Launch Hub with an existing App on one host.
2. Hub starts required processes, attaches them to a designated O, and opens the App in the browser.
3. Confirm that two participating processes observe committed O changes using the existing multiprocess implementation.
4. Read a process's logs through a Hub MCP resource and subscribe to updates.
5. Publish a second Source with an automatically generated `almasi.json` release asset; verify that Hub discovers and starts it from a configured GitHub organization **without changing Hub's implementation**.
6. Stop or crash a supervised process; verify status and recovery behavior.

This validates the architecture before automatic code generation, cross-host placement, or sophisticated resource scheduling.

### Success criteria

The first vertical experiment succeeds only when:
- a repository release produces an index derived from code, without an LLM at discovery time;
- Hub can use an organization name plus a release artifact to identify a capability before downloading the full repository;
- a single user action launches the working environment and opens the intended App;
- Hub introduces no duplicate process or redundant O service;
- a Source is discovered and started without an App-specific modification to Hub;
- two independent O processes exchange committed changes via the existing transport;
- logs are available through the agreed management interface and MCP, with a working client subscription;
- stopping, failing, and restarting a process are visible and follow the defined lifecycle;
- the same mechanisms work without AWS, Kubernetes, or Terraform as prerequisites.

These are **acceptance goals**, not claims of completed tests.


## Open questions

- What is the minimal runnable capability descriptor, and the schema of the generated `almasi.json` release asset?
- How are organizations configured and prioritized; how are trusted repositories, release identities, dependencies, and version conflicts resolved?
- What is the exact boundary between WordWield onboarding/GitHub App authorization and Hub discovery/execution?
- How are O paths, filesystem permissions, credentials, and container isolation provisioned safely?
- Which conditions should trigger automatic generation, and who approves generated code?
- How are log read/subscription permissions, retention, and cursor semantics defined?
- How should one host handle several independent user environments?
- Which verified requirements, if any, justify placement across different hosts?

## Non-goals and traps

- No mandatory AWS-specific orchestration, managed cloud dependency, or Kubernetes compatibility layer.
- No new inter-process O bus or server if the existing shared LMDB and O Transport satisfy the required topology.
- No duplicated business API inside Hub; ordinary calls do not pass through its supervisor.
- No distinct agent logging pipeline when MCP Resources already support the use case.
- No generation of a repository whose required capability is already available.
- No full multi-user application architecture unless a concrete collaboration or trust requirement demands it.
- No global distributed database as an assumed prerequisite for onboarding a second user.

The goal is **necessary symmetry**: unite genuine commonality, retain essential distinctions, remove mechanisms whose sole job is compensating for an artificial separation.


## Status

**Future architecture, canonical name `almasi.hub`.** The shared O multiprocess storage/invalidation mechanism exists in `almasi.o`; a minimal Source/App request-response demonstration exists in `almasi.source` / `almasi.bus`. A general `almasi.hub` orchestrator and its MCP discovery/management interface have **not** been implemented or verified by this document.

The goal is to remove unnecessary infrastructure, not accumulate a new platform in its place.
