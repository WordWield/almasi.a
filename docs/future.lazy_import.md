# Future: Lazy Import of Almasi Libraries

**Status:** Future architecture proposal — not implemented or approved as a production contract.
**Repository:** `apodgorny/almasi`
**Location:** `docs/future.lazy_import.md`
**Context:** Developed while extracting Almasi MCP into a standalone library (2026-11-21).

## 1. Intent

Install Almasi once. Acquire each additional Almasi library only when an application first needs it.

Desired application code:

```python
from almasi import mcp, web, o

class Counter(mcp.Controller):

	@mcp.resource
	async def count(self):
		return 42
```

The expression `mcp.resource` belongs to Almasi MCP. It must **not** require renaming the decorators. The official Python MCP SDK must remain independently installed and updateable under its ordinary `import mcp` namespace.

```python
from almasi import mcp  # Almasi MCP
import mcp as sdk        # Official Python MCP SDK

assert mcp is not sdk
```

The same principle should apply to `almasi.web`, `almasi.o`, and future libraries.

**Core principle:** A library's qualified identity exists independently of whether its source has already been downloaded. A missing library is a resolution problem, not an application-installation chore.

## 2. Background: what already exists

Verified against the Almasi repository at the time of this note:

- The current distribution is named `a`, installed from `pyproject.toml`, and exposes `import a`; it does **not** yet expose a package `import almasi`.
- `a.extend(name)` determines the library's published identity from the defining Python module, checks that the last segment matches `name`, and publishes the library instance in `sys.modules[full_name]`.
- Therefore a source module loaded as `almasi.mcp` with `a.extend('mcp')` can in principle publish `sys.modules['almasi.mcp']` without overwriting `sys.modules['mcp']`.
- `A.__getattr__` already performs *lazy component resolution inside an existing library*, using its filesystem and plugins. It does not currently fetch entire missing libraries.
- `lib/imports.py` already loads Python source by an explicit path using `importlib.util.spec_from_file_location`, with `sys.modules` retaining Python-module identity.
- The existing cache/ownership invariants are documented in `docs/almasi_invariants7.md` and `docs/almasi_invariants8.md`.

**Important distinction:** Lazy loading of a component, lazy acquisition of an Almasi library, and installation of third-party Python dependencies are three separate needs. They should meet at a coherent resolution boundary, without pretending they are the same operation.

## 3. Intended architecture

```text
from almasi import mcp
          |
          v
  Almasi namespace
          |
          v
  Resolve qualified library: almasi.mcp
          |
          +-- locally available ------> load / reuse
          |
          +-- missing --> trusted Almasi hub
                               |
                               v
                        identity -> Git source + revision
                               |
                               v
                        acquire into local Almasi library space
                               |
                               v
                        prepare required dependencies
                               |
                               v
                        load as almasi.mcp
                               |
                               v
                        reuse on subsequent imports
```

The **hub** and **lazy import** are not separate, competing discovery systems. They share one responsibility: resolving an Almasi library identity to an available local implementation.

The hub might initially be a simple index of identities, source URLs and allowed versions/revisions. A hosted service is not a prerequisite for the first experiment.

A conceptual local layout (illustrative, **not** a decided storage contract):

```text
<almasi-library-directory>/
    mcp/          # Checkout of the registered Almasi MCP source
    web/          # Checkout of Almasi Web
    o/            # Checkout of Almasi O
```

The directory layout must not automatically dictate Python import names. The loader must associate the repository's entry file with its **qualified** Almasi identity.

## 4. Proposed implementation methods

### 4.1. Entry point: a small `almasi` import package

Today `pip install -e .` exposes `a` only. To make `from almasi import mcp` real, the base distribution must also ship an importable `almasi` package. Whether the published distribution itself is later renamed from `a` to `almasi` is a separate packaging decision.

For the **specific** form `from almasi import mcp`, start with package-level `__getattr__`. It can call the existing/extended library resolver when the requested attribute is not already available.

Conceptual sketch (NOT the current implementation):

```python
# almasi/__init__.py
# Resolve an Almasi library only when its name is requested.
# ----------------------------------------------------------------------
def __getattr__(name):
	return resolve_library(name)
```

Here `resolve_library` denotes the intended resolution operation, **not** an existing public API. Python also asks packages for special attributes; the resolver must reject unsupported and special names without triggering network access.

The direct form `import almasi.mcp` is a separate requirement: Python's ordinary submodule finder does not invoke the parent's `__getattr__` as its general missing-submodule handler. If direct dotted imports are required, evaluate a narrowly scoped `MetaPathFinder` for `almasi.*`, or a physical package layout satisfying standard import discovery. **Do not add a global import hook before this requirement is demonstrated.**

### 4.2. Use canonical identities; do not claim the SDK's top-level `mcp`

The Almasi library source must be executed under its qualified module identity, e.g. `almasi.mcp`, **not** imported first as top-level `mcp`.

Illustrative library entry point:

```python
# mcp.py, executed as almasi.mcp
import a

mcp = a.extend('mcp')
```

The existing `a.extend()` checks the final module segment (`mcp`) and publishes the full name (`almasi.mcp`). This is the essential bridge between ordinary Python imports and Almasi's library instances.

**Packaging trap:** Giving a distribution the name `almasi.mcp` does not prevent it from shipping a top-level `mcp.py` or `mcp/` package that conflicts with the official SDK. Distribution identity and import namespace must both be checked. A safe early experiment can acquire the Almasi source repository and load its entry point by qualified path, without installing its top-level `mcp` module into site-packages.

Never copy, vendor, patch, alias or mutate the official SDK merely to preserve the Almasi decorator API.

### 4.3. Local resolution first

For a known identity:

1. Return the already published Almasi module/library instance if it exists in `sys.modules`.
2. Otherwise look for an already acquired local source in the designated library space.
3. Only if it is absent, consult the hub and acquire it.
4. Load through the canonical Almasi entry point, allowing existing `a.extend()` and component loading to do their normal work.

Do not maintain a duplicate permanent registry of loaded modules when `sys.modules` already owns that identity. Distinguish physical source availability from a loaded Python module.

### 4.4. Hub discovery

The minimal hub contract should resolve a **qualified** identity such as `almasi.mcp` to:

- An allowed Git repository URL (initially GitHub).
- A pinned revision/tag/compatible version rule.
- An expected source entry point or a conventional library layout.
- A trusted source/publisher identity and acquisition policy.

For the first prototype, a small curated mapping is enough. Later, a GitHub-based Almasi Hub can provide discovery and metadata. Do **not** clone arbitrary repositories computed from unchecked import strings; a typo must not become remote code execution.

Hub unavailability should not prevent using a locally available library.

### 4.5. Acquire once, publish atomically

A proposed acquisition sequence:

1. Resolve the exact trusted source and revision.
2. Coordinate concurrent requests for the same library (including across processes).
3. Fetch into a temporary directory on the same filesystem as the library cache.
4. Verify repository identity/revision and expected Almasi entry point.
5. Prepare dependencies and validate readiness before exposing the source as locally available.
6. Atomically publish the completed local checkout, then release the acquisition lock.
7. Load the library through its qualified name.

If fetching, verification or preparation fails, leave any previously usable local version intact and do not publish a half-installed tree. A successful ordinary import never silently updates an existing local checkout.

Do not add redundant persistent state where Git revision, directory contents and `sys.modules` already provide the needed facts. Use an explicit completion marker only if needed to distinguish a verified installation from an incomplete one.

### 4.6. Dependencies: separate from acquiring Almasi source

The Almasi library itself can be loaded from its checked-out source. Dependencies on external Python packages still need packaging metadata and a real installer (initially normal `python -m pip` in the **active interpreter environment**).

Candidates to compare:

**A. Load checked-out Almasi source by qualified path; use pip only for external dependencies.**
Best starting point for the `mcp` collision: the Almasi source is not exposed as top-level `mcp`. Needs an agreed import contract and dependency metadata.

**B. Install an Almasi distribution with editable/regular pip.**
Useful when the distribution correctly exposes `almasi.mcp` and no conflicting top-level module. A different pip distribution name alone is insufficient. An installation performed after interpreter startup may require import-cache/path refresh; do not assume new `.pth` files are executed retroactively.

**C. Dedicated dependency environments or subprocesses.**
Only if conflicting versions genuinely require isolation. A different install directory alone does **not** isolate `sys.modules`, process globals, or absolute imports.

**Recommended first experiment:** A, using the existing source-layout convention and Almasi's module ownership rules. Keep ordinary pip for third-party packages. The project must explicitly document which interpreter receives dependencies and whether installation during import is permitted.

### 4.7. Loading and cache coherence

After publishing a checkout:

- Resolve its entry point as `almasi.<name>`; do not temporarily import it as top-level `<name>`.
- Ensure Python knows the qualified package/module relationship. A targeted use of `importlib.util.spec_from_file_location` is a candidate; compare it with the existing `Imports.load_module` rather than creating a second general loader.
- Let `a.extend()` own publication of the resulting Almasi instance in `sys.modules`.
- Verify repeated `from almasi import mcp` returns the **same** canonical library instance.
- Ensure a failure during execution cleans up only incomplete module state, not a valid official SDK module or unrelated imports.

`a.extend()` presently publishes a library **instance**, not a conventional `ModuleType`. Check Python importlib behavior with this detail, especially `__spec__`, parent package attributes and `import almasi.mcp`, before promising complete import syntax compatibility.

### 4.8. Updating is not importing

Use an explicit future update operation to fetch a newer approved revision, validate it and activate it at a controlled boundary. Do not reload a live library merely because a repository changed: existing class objects, singleton services, references and cached module identities may already be in use.

Import = resolve the currently selected available version.
Update = choose and install a newer version.
Reload/activation = a separate lifecycle decision.

### 4.9. Security and reproducibility

Import-triggered installation can execute arbitrary Python code through setup/build steps, dependency hooks and module imports. Before enabling this in ordinary applications, define:

- Trusted hub identity and authorized publishers.
- Reproducible revision pins or lock information, with integrity checks.
- User/operator consent policy for first-time network acquisition and package installation.
- Protection from dependency confusion, typos, path traversal and executable source substitution.
- Explicit offline behavior and informative failure messages.
- A stable dependency-resolution policy; incompatible dependency constraints must fail visibly rather than silently corrupt a running environment.

These are not optional implementation details: automatic remote code acquisition is a security boundary.

## 5. Minimal experimental sequence

Implement in increasing order of necessity:

1. **Qualified local load only:** manually place an Almasi MCP checkout in a test directory. Make `from almasi import mcp` load it as `almasi.mcp` without network access. Install the official SDK normally and assert `import mcp` remains independent.
2. **Repeatability:** check module identity and cached Almasi component identity across repeat imports.
3. **Hub mapping:** add one curated identity-to-repository mapping, no search service.
4. **Missing-source acquisition:** fetch that library to a staging directory and publish only after verification.
5. **Dependency preparation:** use a dedicated test virtual environment; install the SDK/dependencies without creating the top-level import conflict.
6. **Failure/concurrency:** test interrupted fetch, invalid source, missing dependency, multiple first imports, no network, and restart with an already acquired local library.
7. **Only if requested:** support `import almasi.mcp` and test Python's full submodule-import semantics, adding a scoped finder only if necessary.

### Acceptance criteria

- `from almasi import mcp` returns an Almasi library with `mcp.resource` and `mcp.tool`.
- `import mcp` imports the unmodified official MCP SDK in the same interpreter.
- The official SDK can be updated with normal pip; Almasi never vendors or edits it.
- A missing *trusted* Almasi library is obtained exactly once per local installation, then reused.
- Failure does not publish a partially installed library or remove a previously working one.
- Repeated imports preserve canonical runtime identity; importing never triggers updates.
- Existing `a` library/component filesystem resolution remains intact.
- Unexpected names do not trigger arbitrary installs.
- All supported public operations have documented lifecycle and dependency requirements.

## 6. Decisions already made vs. open questions

**Intent agreed:**
- The public Almasi family is addressed as `almasi.<library>`.
- `from almasi import mcp` preserves the local variable name and decorator syntax.
- The official `mcp` SDK stays independent and normally updatable.
- Almasi libraries may eventually be acquired from a GitHub-backed hub into one shared local library space.
- This is explicitly **future** work. Current MCP extraction must not depend on implementing it.

**Still open:**
- Exact on-disk library root; per-user vs. per-project cache and environment-specific ownership.
- Whether the base distribution remains named `a` or gains a published `almasi` distribution.
- Exact hub index schema and source verification/trust policy.
- Selected dependency installation mechanism and permitted automatic side effects.
- Version pinning, compatibility rules and offline semantics.
- Whether `import almasi.mcp` must work in addition to `from almasi import mcp`.
- The supported installation/activation lifecycle and concurrency mechanism.

## 7. Historical evidence and limitations

A previous isolated proof of concept demonstrated automatic acquisition during an import and coexistence of Almasi-qualified and top-level SDK-like names under Python 3.13. It used a **mock official SDK and simulated Almasi publication**, not a verified integration of the real `almasi.mcp` repository with the official SDK. Do not treat that test as proof of production readiness.

The actual `apodgorny/almasi.mcp` repository was present but had no readable `mcp.py` or `pyproject.toml` in the checked branch at the time of this note. The MCP extraction remains a separate current task.

The relevant live Almasi source locations inspected for this proposal were `a.py`, `lib/imports.py`, `plugins/py.py`, `pyproject.toml`, and `docs/almasi_invariants7.md` / `docs/almasi_invariants8.md`.

**Do not implement this future feature as part of MCP extraction.** Its purpose here is to preserve the reasoning, design alternatives, constraints and acceptance criteria for a later dedicated development session.

---

**Architecture of Necessary Symmetry:** Identity belongs to the Almasi namespace; local availability belongs to library resolution; remote sources belong to the hub; Python dependency installation belongs to packaging. Their responsibilities meet only where required. No parallel package manager, duplicated module registry or monkeypatching of the official SDK is justified by the intent.
