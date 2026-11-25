# Pip service

`a.services.Pip` is a process-local Singleton bound once to one Entity's requirements file. Pip changes the interpreter environment selected by `sys.executable`; it does not create a virtual environment.

```python
from almasi import a

pip = a.services.Pip
pip.initialize('/absolute/path/to/requirements.txt')
pip.install('beautifulsoup4', min_version='4.12', max_version='4.99')
pip.sync()
versions = pip.list()
snapshot = pip.freeze()
pip.uninstall('beautifulsoup4')
```

- initialize(requirements_path): create a missing .txt file, or install its requirements.
- sync(): install from the current file, without removing undeclared packages or rewriting the declaration.
- install(name, min_version=None, max_version=None): install a distribution with inclusive optional PEP 440 bounds; atomically add or replace its direct declaration after pip succeeds.
- uninstall(name): uninstall the named distribution and atomically remove its direct declaration after pip succeeds.
- list() -> dict[str, str]: installed distribution names and versions.
- freeze() -> str: native pip freeze text; never writes the declaration.

Operations are synchronous; use asyncio.to_thread for long calls on an event loop. Each process binds only its own file. Operations within that service are serialized. The environment is shared with other Entities: package upgrades, downgrades and removals may affect them. No cross-process transaction or dependency conflict isolation is promised. An already imported module may require restart after a version change.

Only simple direct package declarations are edited by install/uninstall; complex declarations (markers, extras, direct URLs) require manual editing. Do not use these mutation methods for requirements containing included files, hashes, continuation lines or editable installs; sync delegates standard requirements syntax to pip. File publication is atomic, but cannot roll back successful pip changes if publication fails. Pip errors propagate, and a failed pip command leaves the declaration unchanged. Use only trusted requirements and package sources.

Git, Hub and Pip do not depend on one another. The Entity owns initialization and deployment sequencing.

For live deployment, the Entity uses `async with a.services.Filesystem.defer_changes(entity.__path__)` around its Git pull and Pip sync. Filesystem defers observer notifications for that watched root, including after a failed sync until the next successful retry. This does not stop active calls, prevent explicit reads from disk, or provide a transaction over the Python environment.
