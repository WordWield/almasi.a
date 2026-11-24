# Almasi Core (`a`)

**What if your codebase was already your runtime architecture?**
Almasi is an open-source Python foundation that turns source structure into a live, composable namespace—without a separate layer of registration and wiring.
**For developers:** fewer moving parts, lazy components, natural composition. **For ambitious products:** a common foundation for persistent state and AI agents.
![Almasi — the winged white elephant dancing with its trunk held high](https://raw.githubusercontent.com/WordWield/almasi.a/master/assets/almasi-elephant.png)

[Watch the 2-minute overview](https://www.youtube.com/watch?v=eCk6kiAriR0) · [Persistent objects: Almasi O](https://github.com/WordWield/almasi.o) · [Agents: Almasi Do](https://github.com/WordWield/almasi.do)

## See it in 30 seconds

Install from PyPI (Python 3.11+):

```bash
python -m pip install almasi
```

Use a library as if it were part of the runtime:

```python
from almasi import o

print(o)  # <Library 'almasi.o'>
```

On first access, Almasi retrieves the library's Git source, installs its declared dependencies and publishes its canonical Python namespace. Repeated imports reuse that instance. **The installed loader stays small; even Core arrives when needed.** Git and internet access are required for first acquisition.

Or define a filesystem-native library yourself:

```text
mylib.py
root/
└── greetings.py
```

```python
# mylib.py
from almasi import a

mylib = a.extend('mylib')
```

```python
# root/greetings.py
import mylib

class Greetings(mylib.Module):

	def hello(self):
		return 'Hello from the filesystem'
```

```python
import mylib

print(mylib.Greetings().hello())
```

A file becomes a module in the runtime namespace when it is needed. No manual registry of `greetings`, no generated integration layer.

## The idea

Most frameworks describe the same system repeatedly: files, package exports, service registries, plugin registries, dependency wiring and application configuration. Each representation can drift from the others.

**Almasi makes the filesystem a first-class source of runtime structure.** Its libraries are canonical instances of classes, with inheritance, lazily resolved components and extensible file-type plugins.

| Capability | What it changes |
| --- | --- |
| Filesystem-native namespaces | A `root/` tree resolves naturally into a Python library namespace |
| Library inheritance | Extend a library without copying its components |
| Lazy resolution | Discover and cache components on access |
| Pluggable file semantics | Load Python, JSON, text and other supported resource types through plugins |
| Named forks | Isolate runtime classes, services and module globals within a library lineage |
| On-demand library acquisition | Retrieve WordWield libraries and their dependencies on first import |

### A family, not a monolith

**[Almasi Core](https://github.com/WordWield/almasi.a)** — runtime identity, filesystem-native discovery and library composition.

**[Almasi O](https://github.com/WordWield/almasi.o)** — a persistent Python ontology: typed entities, identity, relationships, nested collections, schemas and LMDB-backed state.

**[Almasi Do](https://github.com/WordWield/almasi.do)** — AI agents, structured outputs and provider orchestration that build on the same runtime and object model.

The larger opportunity is architectural: applications and agents can build on shared native primitives instead of maintaining an ever-growing web of translations. Almasi is active infrastructure research and development, not a claim that every integration has already been completed.

## How it works

A library entry point declares its name through `extend()`:

```python
from almasi import a

mylib = a.extend('mylib')
```

The entry file and library name must match, and a sibling `root/` directory must exist. Components stored under `root/` are resolved by their names, loaded when accessed and cached. Python components are classes derived from `Module`; other supported files use registered plugins.

Libraries inherit the capabilities of their parent:

```python
from almasi import o

# In the entry point of an appropriately named child library:
# child = o.extend('child')
```

When a library is extended from `__main__`, Almasi also selects it as the active application. Application selection is process-wide; services do not implicitly initialize merely because a library is extended.

### Namespace fallback

A library can delegate missing public attributes to an ordinary Python object:

```python
from types import SimpleNamespace

mylib.__fallback__ = SimpleNamespace(remote='external value')
assert mylib.remote == 'external value'
```

`__fallback__` defaults to `None` (disabled). Existing Python attributes and
native filesystem resolution always take precedence. Library acquisition is
independent and belongs to the installed loader. If native lookup finds no component, the
library returns `getattr(library.__fallback__, name)` for public names
(names not beginning with an underscore). The result is not cached as a
filesystem component, even when it is `None`. AttributeError from the
fallback propagates normally. Assign `None` to disable it again.

The fallback is configured on one library face, not its directories,
children or forks. Install it separately on a fork if needed. This is a
namespace extension, not a second filesystem resolver.

### Named forks

```python
alice = mylib.fork('alice')
bob   = mylib.fork('bob')

assert alice is not bob
assert mylib['alice'] is alice
```

Forks isolate Python-side runtime namespaces and service instances. They **do not** automatically duplicate external databases or other application-owned resources. Those lifecycle choices belong to the consuming library.

### Filesystem operations

The runtime also provides `join()`, `mkdir()`, `read()`, `write()`, `copy()` and `link()` on directory faces and library roots. Writes and copies use atomic replacement, and successful mutations invalidate affected cached filesystem carriers. [Read the detailed invariants](docs/almasi_invariants8.md).

## Git repository management

Core provides [Git checkout and GitHub repository operations](docs/git.md) through `a.services.Git`.

## Acquisition and security

```python
from almasi import o, do
```

Missing libraries are resolved from the default Git base `https://github.com/WordWield` and stored under `~/.cache/almasi/libraries`. Existing checkouts may be fast-forwarded on first import in a process. The loader installs a library's `requirements.txt` into the **active Python environment**.

| Setting | Effect |
| --- | --- |
| `ALMASI_PATH` | Choose the directory for library checkouts |
| `ALMASI_GIT_BASE` | Choose a Git source base, including SSH URLs |

Only libraries accessible with your Git credentials can be acquired. Git revisions are currently **not pinned or cryptographically verified**; imports execute source code and may install Python packages. Use only repositories you trust. This is convenient for development and experimentation, not a sandbox for untrusted code.

The supported library entry layouts are `<checkout>/<name>.py` and `<checkout>/almasi/<name>.py`, each with a `root/` directory. The latter preserves unrelated top-level packages such as the official Python `mcp` SDK. The supported lazy-import contract is `from almasi import name`, not direct `import almasi.name`.

## For builders and collaborators

Almasi explores a focused thesis: **complexity should emerge from necessity, not from duplicate representations of the same concept.**

This is relevant to AI-native applications, agent infrastructure, developer tooling and software that needs persistent, inspectable structure. The three libraries demonstrate distinct layers of that thesis; there are no claimed adoption or benchmark numbers beyond published project tests.

- [Source and issues](https://github.com/WordWield/almasi.a)
- [Architecture and invariants](docs/almasi_invariants8.md)
- [Python CI](https://github.com/WordWield/almasi.a/actions/workflows/python-tests.yml)

## Project status

Python 3.11+; Apache-2.0. Core is acquired from Git by the [Almasi loader](https://github.com/WordWield/almasi). Install the loader with `pip install almasi`, then use `from almasi import a`. The split requires loader 0.2.0 or later.

**Created by Alexander Podgorny** — AI systems architect and researcher. [Connect on LinkedIn](https://www.linkedin.com/in/podgorny/).
