# Almasi

**A filesystem-native Python runtime for building and composing libraries.**

[Watch the 2-minute technical overview on YouTube](https://www.youtube.com/watch?v=eCk6kiAriR0&utm_source=chatgpt.com)

Almasi makes the **filesystem itself the structure of a Python library**.

Instead of maintaining separate registration, discovery, and integration layers, Almasi resolves components directly from the library's filesystem structure and exposes them through a native Python namespace.

The result is a development model where **the structure of the codebase becomes the structure of the runtime**.

## Core Ideas

### Library = Class

An Almasi library is backed by a Python class and a canonical published instance, but is declared with `extend()` rather than a class definition.

In `mylib.py`:

```python
import a


mylib = a.extend('mylib')
```

To build a library on top of another, use `mylib = parent.extend('mylib')` in the corresponding module. The resulting library class inherits from the parent's class, and namespace lookup follows that lineage. Library creation does **not** implicitly invoke `initialize()`; the application explicitly initializes the services it needs.

When `extend()` is called directly from Python's `__main__` module, the resulting library is selected automatically as the application:

```python
web_app = web.extend('web_app')
```

The selected application is stored as `a.__app__`. Every Almasi `Module` instance — including `Singleton` and event-controller instances — inherits `self.__app__` from the `Module` base class. This property resolves the current application at access time, so objects created before application selection also see it. `self.__lib__` identifies the library that defined the class, independently of `self.__app__`. The loader does not inject an application global into Python modules.

```python
class Example(web.Module):

	def execute(self):
		return self.__app__.services.SomeService
```

Application selection is process-wide, not per request. Before selection, `self.__app__` returns `None`. Since selection follows `__main__`, a script calling `extend()` directly is also treated as an application.

### Filesystem → Namespace

A library's filesystem structure maps directly to its Python namespace:

```text
mylib/
└── root/
    ├── foo/
    │   ├── bar.py
    │   └── config.json
    └── README.txt
```

```python
import mylib

mylib.foo.bar
mylib.foo.config
mylib.README
```

Components are resolved lazily when accessed.

### Lazy Runtime Resolution

Almasi discovers components on demand:

```text
mylib.foo.bar
       │
       ▼
   filesystem
       │
       ▼
   resolve → load → cache
```

Python modules must inherit from `Module` to participate in the runtime:

```python
import mylib


class Bar(mylib.Module):

	def hello(self):
		print('Hello from Bar')
```

### Extensible Plugins

Filesystem resolution is separated from file semantics through a plugin system.

Plugins can define how different resource types are discovered and loaded:

```python
class Json(a.Plugin):

	EXTENSIONS = ('json',)

	def __call__(self, name, parent_path, parent_route):
		...
```

The runtime can therefore be extended without changing its core resolution model.

### Library Composition

Libraries remain ordinary Python modules and can be composed through normal imports:

```python
import mylib
import other_lib

mylib.foo
other_lib.bar
```

Each library maintains its own structure and namespace while participating in the same runtime model.

### Forked runtime namespaces

Named forks isolate Almasi's lazy Python module globals, runtime classes, service
singletons, and namespace caches without publishing another canonical Python
library. Forks may themselves be forked.

```python
import mylib

alice = mylib.fork('alice')
bob   = mylib.fork('bob')

assert mylib['alice'] is alice
assert mylib['default'] is mylib
assert alice is not bob  # Each fork resolves its own Python components
```

Inside Python files loaded through a fork, `import mylib` (and imports of
inherited library names) resolves to that fork. The ordinary application-level
`import mylib` remains canonical, so use `mylib['alice']` to select the fork
at the application boundary. Python code objects are reused between forks,
but their classes and module globals are separate. The default library keeps
its existing loader and cache behavior.

The fork starts with fresh component caches and deep-copied ordinary public
configuration values. Already resolved Python classes, bound methods, and
service instances are not inherited. Library-specific lifecycle and external
storage (for example an LMDB snapshot) belong to the consuming library's
`fork()` override; Almasi does not clone persistent storage.

## Files and directories

Almasi carriers expose identity through `get_path()`, `get_route()`, `get_lib()`, and `get_name()`. `is_directory()` is a method. Ordinary names such as `path`, `name`, `lib`, and `data` remain available to filesystem children.

```python
docs = mylib.mkdir('docs')

docs.write('intro.md', '# Welcome')
docs.write('notes.txt', 'Hello, world!')
mylib.write('scenario.json', {'title': 'Python Demo', 'scenes': []})
docs.copy('narration.wav', source_filename)

intro    = docs.read('intro.md')
notes    = docs.notes
scenario = mylib.scenario
filename = docs.join('images', 'cover.png')
```

| Method | Semantics |
|---|---|
| `join(*parts)` | Validate a relative path without creating anything; `join()` returns the base |
| `mkdir(*parts)` | Create directories and return a native directory face |
| `read(name)` | Read an exact filename through its registered plugin |
| `write(name, value)` | Serialize through a plugin and atomically replace the destination |
| `copy(name, source)` | Copy regular-file bytes and atomically replace the destination |
| `link(name, path)` | Create or retarget a filesystem mount |

All six operations are also available on the library root. Paths must remain contained; absolute components, escaping traversal and unintended symlink writes are rejected. `write` supports UTF-8 `.txt` / `.md` and JSON; `copy` supports binary files and unknown extensions without serialization. Errors propagate as exceptions.

Atomic writes and copies publish completed hidden temporary files with `os.replace`. Failures before replacement preserve the old destination and clean up temporary files. Atomic replacement does not promise power-loss durability. Successful mutations invalidate related carriers in the receiving namespace face while preserving unrelated cached resources. JSON `null` is memoized. Independently constructed faces and external edits are not globally refreshed.

See [the current filesystem invariants](docs/almasi_invariants8.md) for identity, reserved names, inheritance and cache scope.

## Qualified Almasi library imports

The core installs both the canonical `a` library and the `almasi` namespace:

```python
from almasi import web, o, mcp
```

The package-level `almasi.__getattr__` delegates to the native
`a.services.Libraries` Singleton. A library is loaded under its qualified
identity, such as `almasi.mcp`, and `a.extend('mcp')` publishes the canonical
instance in `sys.modules`. The official MCP SDK retains the unrelated top-level
`import mcp` identity.

```text
from almasi import web
    -> Libraries.imp('web')
    -> reuse sys.modules['almasi.web'], if already loaded
    -> reuse an existing local checkout, if available
    -> otherwise clone WordWield/almasi.web into the library directory
    -> load the entry file as almasi.web
    -> reuse the same canonical instance on subsequent imports
```

No manual `Libraries.initialize()` call or separate installation of each
Almasi library is necessary. The default source directory is
`~/.cache/almasi/libraries`, with optional settings:

| Environment variable | Purpose |
| --- | --- |
| `ALMASI_PATH` | Override the directory containing acquired libraries |
| `ALMASI_GIT_BASE` | Override the Git source base; default `https://github.com/WordWield` |

For example, `ALMASI_GIT_BASE=git@github.com:WordWield` uses SSH
authentication. Private repositories require suitable Git credentials.

The supported library layouts are `<checkout>/<name>.py` and
`<checkout>/almasi/<name>.py`, both with a `root/` directory.
The nested entry point preserves independent top-level Python packages,
particularly the official MCP SDK. Checkout acquisition uses a temporary
sibling directory; only a complete source tree is published. A successful
import never updates an existing checkout.

| Method | Contract |
| --- | --- |
| `get_path(name)` | Resolve the local checkout path |
| `get_url(name)` | Derive the configured Git source |
| `is_cloned(name)` | Check for a usable local checkout |
| `clone(name)` | Acquire the checkout when absent |
| `imp(name)` | Reuse or load the canonical Almasi library |

Git handles authentication. Libraries does not currently install third-party
Python dependencies, pin or verify Git revisions, or guarantee that private
repositories are accessible. Install any required external packages in the
active Python environment before using dependent components. Importing a
library executes its Python source; only trusted repositories should be used.

This namespace supports `from almasi import <name>`. Direct
`import almasi.<name>` uses Python's distinct submodule import mechanism
and is not part of this contract.

## Installation

For development, install the core directly from its Git repository:

```bash
git clone https://github.com/WordWield/almasi.git
cd almasi
python -m pip install -e .
```

The current distribution metadata still uses the name `a`.
PyPI publication and production-wheel packaging are separate release steps;
the source-acquisition behavior is identical once the core is installed.

## Author

**Alexander Podgorny**

AI architect and systems researcher.

[LinkedIn](https://www.linkedin.com/in/podgorny/?utm_source=chatgpt.com)