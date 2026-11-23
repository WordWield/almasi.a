# Almasi Architecture — Distribution and On-Demand Libraries

**Status:** Current core contract, with future application-workspace decisions explicitly separated.
**Repository:** `WordWield/almasi`
**Established:** 2026-11-22

## Intent

A single `pip install almasi` provides the small, stable Almasi core. The rest of the ecosystem remains independent Git repositories, acquired only when needed. The Python namespace is the interface: the developer asks for a library, not for a separate installer, registry, or import wiring.

> Install the core once. Resolve each library on demand. Reuse its canonical runtime identity.

## Distribution boundaries

| Concern | Owner | Contract |
| --- | --- | --- |
| Core distribution | PyPI package `almasi` | Installs the runtime, filesystem resolution machinery, and core dependencies into the active Python environment |
| Library source | `almasi.<name>` Git repository | Independently versioned source, fetched on first use |
| Library acquisition | `a.services.Libraries` | Resolve source path, clone or update, prepare dependencies |
| Python identity | `almasi.Imports` and `A` | Load and publish the canonical `almasi.<name>` library; preserve in-process identity |
| Library internals | Its own `root/` tree | Resolve filesystem-backed components lazily through the existing Almasi namespace |
| Application workspace | Application owner/developer | Own a working checkout; an application is not a library silently cloned into the shared cache |

The core is currently packaged from `almasi.py` plus its supporting `lib/`, `root/`, and `plugins/` trees. Installing it with pip does **not** create a Git checkout in the developer's current directory, nor does it download all optional libraries.

## Library resolution

The supported call is:

```python
from almasi import o
```

For a library not yet resolved in this process:

1. The root Almasi namespace receives attribute access through `A.__getattr__`.
2. The existing `a.services.Libraries.imp(name)` service checks `sys.modules['almasi.' + name]`.
3. If the library is not loaded, `Libraries` reuses its existing checkout or clones a missing one.
4. If an existing checkout has `.git`, `Libraries` attempts `git pull --ff-only` before loading.
5. If the checkout contains `requirements.txt`, its requirements are installed with `sys.executable -m pip install -r ...` into the **active environment**.
6. `Imports.load_module(..., module_name='almasi.' + name)` loads the entry point with its canonical module name.
7. The entry point uses `almasi.extend(name)` to publish the library instance. `Libraries.imp` checks that this is an Almasi library and returns it.
8. Later imports in the same process reuse the published object rather than reacquiring and re-executing it.

```text
pip install almasi
       │
       ▼
Installed core (almasi.py + lib/ + root/ + plugins/)
       │
       │  from almasi import o
       ▼
A.__getattr__ → services.Libraries.imp('o')
                          │
                  existing sys.modules?
                    │            │
                   yes           no
                    │            ▼
                    │       cache / git clone
                    │            │
                    │       optional git pull
                    │            │
                    │       requirements.txt
                    │            │
                    │       Imports.load_module
                    └────────────┘
                          │
                          ▼
                Canonical almasi.o library
```

This is attribute-based acquisition, **not** a global Python import hook or a modification to `sys.path`. The supported convenience contract is `from almasi import name`; direct `import almasi.name` is not guaranteed by this mechanism.

## Source and local paths

A logical library name `name` maps by default to:

```text
Git:    https://github.com/WordWield/almasi.<name>.git
Local:  ~/.cache/almasi/libraries/almasi.<name>/
```

The existing configuration surfaces are:

- `ALMASI_GIT_BASE`: replace the default Git base (including SSH-based access).
- `ALMASI_PATH`: replace the parent directory for library checkouts.

Both are interpreted by `Libraries`; they do not create a second package registry. Git credentials govern access to repositories that are not public.

Supported entry-point layouts within a checkout are:

```text
almasi.<name>/<name>.py
almasi.<name>/root/
```

or:

```text
almasi.<name>/almasi/<name>.py
almasi.<name>/root/
```

The nested layout permits a library such as `almasi.mcp` without taking over an unrelated top-level Python package such as the official `mcp` SDK.

## Two different kinds of laziness

**Library acquisition is lazy:** Git acquisition, dependency preparation, and entry-point import happen when a library is first requested in a process. Already-loaded libraries keep their Python identity.

**Component resolution is lazy:** Within an acquired library, names from its `root/` filesystem namespace are resolved and cached on access, using the existing library inheritance and plugin mechanisms.

These are distinct responsibilities. There is no second component registry, and the Git acquisition service does not implement the filesystem resolver.

## Applications and development workspaces

An **application** is different from a reusable library. The intended development flow clones an application repository into a developer-controlled working directory, where it can be edited, tested, and run. It is **not** automatically acquired through `from almasi import ...` into the shared library cache.

When an Almasi library is extended from the process's `__main__` module, the core selects that library as the active application. That is runtime selection, not a Git workspace manager.

For Almasi Projects, the repository naming decision is separate from core library acquisition:

```text
<owner>/almasi.app.<project>
<owner>/almasi.source.<source>
```

An App belongs to its project. A Source is independently owned and may be used by multiple Apps. Both are editable development workspaces, with shared backend structure and lifecycle; only App additionally has browser/static components. This is an agreed architectural direction, **not** a claim that the core already provisions these repositories.

A future CLI such as `almasi o path` or `almasi o test` may expose source location and testing without duplicating the underlying library services. These commands are **not** part of the currently verified CLI contract.

## Release and installation lifecycle

The core has one `pyproject.toml` describing the PyPI package and its direct dependencies. Publishing it does not require publishing each Almasi library as its own PyPI package.

The repository's `.github/workflows/publish.yml` currently:

1. Runs on a published GitHub release.
2. Builds the wheel and source distribution.
3. Checks distribution metadata with Twine.
4. Publishes to PyPI using the `pypi` environment and GitHub OIDC Trusted Publishing, rather than a long-lived PyPI token.

A new core release changes the installed bootstrap/runtime. A change in a library repository is a distinct lifecycle: an existing checkout may be fast-forwarded on first use in a later process. Updating files **does not** automatically reload already-published Python modules in a running process. Runtime hot reload is a separate mechanism.

## Invariants and limits

1. **One canonical identity:** loading a library must preserve its `almasi.<name>` identity and reuse the already-published instance within a process.
2. **No eager ecosystem installation:** importing the core does not clone or install every library.
3. **One source of library location:** Git naming and the two environment overrides determine acquisition; no parallel catalog is maintained.
4. **No duplicate imports machinery:** `Libraries` acquires and prepares; `Imports` executes and publishes. Neither replaces the other's responsibility.
5. **No implicit developer workspace:** a cached library checkout and a separately editable application checkout have different purposes.
6. **No silent identity reset:** changes in Git do not replace an already-loaded library in the same process.
7. **Trust boundary:** acquiring a library executes Git-sourced Python and may install its dependencies. Git revisions are not currently pinned or cryptographically verified; this mechanism is for trusted repositories, not a sandbox.
8. **Update fallback:** a failed pull of an already-cloned repository produces a warning and uses the local checkout; initial clone, dependency-installation, and import failures are not equivalent to an available, working library.
9. **Concurrency is not yet guaranteed:** a shared cache path does not by itself establish locking or transactional cross-process clone/update semantics. Do not claim them without a test.

## Verification

The observed lazy-loading smoke test used `from almasi import o` after installing Almasi in a Python environment. Before that import, `almasi.o` was neither loaded nor cloned; afterward it was loaded and cloned, with its root in `~/.cache/almasi/libraries/almasi.o/root`. The test reported `PASS: lazy loading and reuse work`.

This verifies that scenario, not all network, permissions, concurrency, offline, or upgrade behavior. Future changes to distribution should preserve the listed invariants and retest from a clean environment.

## Relevant implementation

- `pyproject.toml` — installed core and direct dependencies
- `almasi.py` — canonical library identity and `A.__getattr__`
- `root/services/libraries.py` — Git acquisition, cache paths, dependency preparation
- `lib/imports.py` — explicit Python module loading
- `.github/workflows/publish.yml` — PyPI Trusted Publishing
- `README.md` — supported installation and user-facing constraints
