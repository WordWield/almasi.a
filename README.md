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

The base distribution also ships the `almasi` Python import namespace.
No second Almasi distribution or global import hook is needed:

```python
from almasi import web

# A canonical Almasi library instance, once its source is available.
assert web.__name__ == 'almasi.web'
```

The `Libraries` Singleton is owned by the Almasi core. The public
operations are available as `a.Libraries` or `almasi.Libraries`:

| Method | Return | Behavior |
| --- | --- | --- |
| `list()` | `list[str]` | Names of locally acquired, already loaded, and discoverable remote libraries |
| `clone(name)` | `str` | Path to a complete checkout, cloned once when missing |
| `imp(name)` | Almasi library instance | Reuse the published `almasi.<name>`, load local source, or acquire and load missing source |

`from almasi import web` uses package-level `__getattr__`, which delegates
to `Libraries.imp('web')`. Existing `a.extend()` publishes the canonical
instance in `sys.modules`; there is no parallel loaded-library registry.
Direct `import almasi.web` is **not** an API guaranteed by this entry point.

By default, `Libraries` searches repositories named `almasi.<name>`
owned by GitHub account `apodgorny`. Its source and checkout location can
be configured without changing library code:

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `ALMASI_LIBRARY_OWNER` | `apodgorny` | GitHub account or organization containing libraries |
| `ALMASI_LIBRARY_DIR` | `~/.almasi/libraries` | Shared local checkout directory |

Remote discovery uses GitHub's public REST API without a login. If an
already-authenticated `gh` CLI is available, `list()` can also discover
private repositories visible to that login. **SSH keys alone cannot list
private GitHub repositories via the API**: a known private
`almasi.<name>` can still be acquired by `clone(name)` or `imp(name)`
using the local Git/SSH credentials. No OAuth flow or Almasi Auth service
is invoked by Libraries.

A locally acquired library loads offline. Failed or incomplete clones
never become available as a valid local source. Import does not update
existing checkouts. If a Python dependency required by an acquired
library is missing, install it into the current Python environment
separately; this initial loader is not a pip dependency manager.

**Security:** importing a cloned Python library executes its code.
Only configure owners you trust. Repository name and entry-point checks
do not verify source integrity or pin a revision. A production hub needs
an explicit trust, revision, and dependency policy before accepting
untrusted publishers.

The current pip distribution name remains `a` while downstream Almasi
packages still declare that dependency. This change adds the `almasi`
*import namespace* to the same installation; migration of the published
distribution name to `almasi` must be coordinated with those packages.

## Installation

Clone the repository and run the included installer:

```bash
git clone https://github.com/apodgorny/almasi
cd almasi
./install.sh
```

## Author

**Alexander Podgorny**

AI architect and systems researcher.

[LinkedIn](https://www.linkedin.com/in/podgorny/?utm_source=chatgpt.com)