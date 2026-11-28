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

### Deployment name

After `extend()`, `library.get_deployment_name()` returns the suffix of the
physical checkout directory named `almasi.<library>.<deployment>`, or the
library's short name when that prefix is absent. For example, a Source
library in `almasi.source.weather` returns `weather`; the standalone
`almasi.source` returns `source`. The name is derived without Git access
or extra initialization; it does not change the Python library identity.
Hub validates its managed names separately.

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

The runtime also provides `join()`, `mkdir()`, `read()`, `write()`, `copy()` and `link()` on directory faces and library roots. Writes and copies operate directly on the destination and invalidate affected cached filesystem carriers. [Read the detailed invariants](docs/almasi_invariants8.md).

## Git repository management

Core provides [Git checkout and GitHub repository operations](docs/git.md) through `a.services.Git`.
For Python dependencies, use the [Pip service](docs/pip.md), `a.services.Pip`.

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


## Method reflection and strict calls

Reflection is available independently of module lifecycle through
`a.Reflection`. `a.Module` inherits `a.Reflection`, and its metaclass
`a.ModuleMeta` inherits `a.ReflectionMeta`. ReflectionMeta reads source
metadata without publishing it; ModuleMeta owns its publication during class
creation. Reflection does not allocate Module instance IDs or require an
active application. Source-backed Almasi components still derive from Module.

Both Reflection and Module instances provide the same reflection API:

- `__get_method__(name, **attributes)` returns a public class-declared bound
  method matching the declaration attributes, or None. Does not evaluate properties.
- `__list_methods__(**attributes)` yields the same matching methods, including
  inherited declarations. An ordinary override replaces the inherited declaration.
- `__get_method_signature__(name)` is a class method returning a dictionary with resolved
  annotations in `inputs` and `output`. Call on a class or instance with the
  method name. The defining class supplies annotation names and the descriptor
  determines the implicit receiver. Unannotated values have no `type` key.
  Missing methods raise AttributeError; non-method declarations raise TypeError.
  Properties and other arbitrary descriptors are not executed.

`a.base.Strict` checks and decorates public methods declared by its subclasses
at class definition. Inherited checked methods remain decorated; public methods
in non-Strict base classes remain unchanged. Private and framework methods
(names beginning with `_`) are excluded. No explicit invocation API is needed.

```python
from almasi import a


class Calculator(a.base.Strict):

	def add(self, left: int, right: int = 1) -> int:
		return left + right


calculator = Calculator()
assert calculator.add(2) == 3
```

Public method declarations require annotations on every input except the
implicit receiver and on the result. Missing annotations fail at definition.
The wrapper stores an ordered `__signature__` dictionary, excluding the implicit
receiver. `inputs` maps names to descriptors with `type`, optional `default`,
and optional `kind` (`positional_only`, `keyword_only`, `var_positional`, or
`var_keyword`; omitted means positional-or-keyword). `output` is a descriptor
with `type`. Python binding checks call syntax and supplies defaults; the dict
controls type checks through `__validate_input__(signature, arguments)` and
`__validate_output__(signature, output)`. Use `__get_method_signature__(name)`
for reflection, not `inspect.signature`, which rejects a dict in `__signature__`.
Treat published signature dictionaries as read-only. Sync, async, class and static
methods retain their ordinary call semantics. No argument names are reserved.

Supported checks: ordinary classes (Python subclass semantics), Any,
unions, Annotated (underlying type), Literal, list/set/frozenset, dict,
tuple, and native Resource carriers (carrier only, never a consuming read).
Unsupported annotations raise TypeError when checked. Reflection alone
does not authorize or publish a method. No protocol semantics are implied.

### Python annotations

`a.Annotation(declaration)` interprets Python type declarations independently
of O. `matches(value)` checks without coercion or resource reads; `cast(value)`
performs the existing explicit data conversion (including coercive primitive,
list, dictionary and union casts). `annotate(value)` infers the declaration of
ordinary Python values. Inference and casts retain the existing finite-number
restriction for data values.

`to_source()` renders the supported annotation forms as trusted Python
expressions. Constructing Annotation from a string evaluates a trusted
expression in the owning namespace; never pass untrusted strings to this API.
An O-specific descendant resolves persistent O addresses. Display, canonical
IDs and deterministic hashes retain their established notation; do not use
annotation IDs as a substitute for runtime type checks.

```python
from almasi import a

annotation = a.Annotation(list[int])
assert annotation.matches([1, 2])
assert not annotation.matches(['1'])
assert annotation.cast(['1']) == [1]
```
