# Future: Python file resolution by naming convention

## Intent

Make Python files accessible through the existing Almasi directory namespace without requiring a separately named import operation.

This is an architectural idea for later exploration, not an implementation plan.

## Proposed semantics

- `directory.Person` resolves the Python class `Person` from its conventional module. Missing expected classes remain errors.
- `directory.person` resolves a resource representing `person.py` rather than trying to load a class.
- `directory.person.py` loads the Python module, without requiring a class of the same name.

The case convention expresses what the caller intends: a class or a file. The `.py` property expresses the action of importing that file.

## Ownership

The existing Python plugin's `Py.__resolve__()` is the candidate point for differentiating `CamelCase` and `snake_case`. `Directory.__getattr__()` already delegates resolution, so it should not require a second mechanism.

Reuse existing module loading and caching. Do not implement another file loader.

## Invariants

- Preserve class resolution behavior and errors for `CamelCase`.
- Preserve library inheritance and local-file precedence.
- Reuse existing module caching and execution context.
- Preserve behavior of ordinary files and directories.
- Avoid redundant wrappers and parallel loading state.

## Open questions

- Which resource object should `snake_case` return, and how should its dynamic `.py` property be implemented?
- How do we avoid conflicts with existing directory attributes, files, and names?
- How should inherited files retain the correct library context and logical route?
- How do explicit filenames with `.py` interact with attribute-based resolution?
- Can this eventually replace `Directory.import_python()` without breaking existing callers?

## Status

Deferred. No code changes are proposed or implied by this document.
