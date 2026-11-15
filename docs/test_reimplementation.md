# Test reimplementation — Almasi, O, Web

**Status:** agreed architectural direction; implementation not started.
**Date:** 2026-11-15.
**Scope:** coordinated test infrastructure migration in `almasi`, `o`, and `web`. This document is an implementation brief, not a claim that the repository already implements the design.

## 1. Intent

Make test execution as ordinary and explicit as possible. Keep the existing Almasi test model and its familiar output. Remove the requirement that tests live inside the runtime namespace, and remove the automatic execution of tests belonging to ancestor/dependency libraries.

The architecture follows Necessary Symmetry: preserve one genuinely shared test execution mechanism, but keep a library's tests and runtime initialization local to that library. A dependency's code may be inherited; its test suite must **not** be inherited.

**Do not replace `a.Tester` with pytest or unittest.** Those frameworks introduce a parallel test model, conventions, fixtures, hooks, and hidden behavior without a demonstrated need. Do not build a wrapper around either framework.

**Do not duplicate test-running code** across individual test modules, across `tests.py`, or across libraries.

## 2. Agreed repository layout

Each repository uses the same structural convention:

```text
almasi/
    lib/                   # Almasi implementation, including lib/tester.py
    root/                  # Runtime namespace; no tests or test runner
    tests/                 # Tests and their fixtures
        test_*.py
        fixtures/
    tests.py               # Run this library's complete Python test suite

o/
    root/                  # O runtime namespace; no test-only modules
    tests/
        test_*.py
        _test_*.py         # Existing explicit benchmarks; not part of normal suite
        fixtures/
    tests.py

web/
    root/                  # Web runtime namespace; no native tests
    tests/
        test_*.py
        browser.test.cjs   # Existing Node/browser tests may stay here
        ...                # Other integration scripts and fixtures
    tests.py
```

The name is **`tests.py`**, plural, at repository top level. It replaces the existing `root/test.py` in each library. It is distinct from the `tests/` directory.

All tests now under `root/tests/` move to the top-level `tests/` directory. Do not create a second tests directory. Preserve their test logic and fixtures unless an actual import/path/lifecycle change requires modification.

`root/` must contain only elements genuinely belonging to the runtime library namespace. In particular, investigate and remove O's test-only `root/tester.py` from that namespace without losing its store-isolation behavior.

## 3. Intended command-line contracts

From a repository root:

```bash
py tests.py                      # All standard Python tests of this library only
py tests/test_file.py            # This test module only
py tests/test_sync.py            # O example: this module only
py tests/_test_performance.py    # Explicit benchmark, when suitable arguments supplied
```

The commands above describe the target interface, not verified current behavior. Running a Python test file directly must work **without** requiring a prior `py tests.py` run or a separately initialized process.

Each existing test class already tends to end with:

```python
if __name__ == '__main__':
    TestFile.run()
```

Keep this simple explicit entry point, with formatting adjusted to the repository style. It should call the same `a.Tester` execution path used by `tests.py`; it must not contain a copy of test discovery, assertion execution, reporting, or O's setup.

Individual test-method selection (such as `::test_name`) was floated earlier but **not approved** as a requirement. Do not implement a CLI parser or selection syntax merely for hypothetical convenience. The required selection granularity is *one module* or *all standard modules*.

`tests.py` is an aggregate launcher, not a second test engine. It delegates to `a.Tester` and does no manual assertion execution. Keep existing output style, including per-class/per-method success marks, headers, and aggregate counts, unless a genuine functional constraint requires adjustment.

## 4. Discovery: known location, bounded enumeration

The repository layout is fixed by convention, so there is **no search for a test namespace, parent libraries, or possible test directories**.

The all-tests entry point resolves its own repository root and uses exactly `<repository>/tests/`. It still needs to enumerate the test modules **within** that one directory. That is simple local enumeration, not framework-style discovery.

Candidate normal-suite files follow `test_*.py`. Existing `_test_*.py` scripts are performance or diagnostic scripts and must not enter normal correctness runs accidentally.

Use Python's standard import mechanisms where necessary. Determine module names/import strategy deliberately: adjacent test modules and fixtures must be importable without collisions, and test imports must not cause accidental execution. Do not introduce a new Almasi namespace layer for the moved test files.

The all-tests invocation must run only the current repository's tests. Remove the `a.Tester` behavior that iterates `cls.__lib__.__instances__()` to run library layers. A's, O's, and Web's own CI pipelines remain responsible for their suites; consumers test integration contracts they rely on.

## 5. Existing code: verified starting point

At the time this note was written, inspection of repository source showed:

- `almasi/lib/tester.py`: `Tester(Module)` has `roots()`, `clean_fs()`, route helpers, `run_layer(instance)`, and `run()`. Aggregate `run()` reverses and iterates `cls.__lib__.__instances__()`; `run_layer()` takes tests from `instance.tests` when `<instance.__path__>/tests` exists. Class execution recognizes `@classmethod` names starting with `test`.
- `almasi/root/test.py`: `import a; a.tester.run()`.
- `almasi/root/tests/test_core.py`: subclass of `a.Tester`, with an existing direct `if __name__ == '__main__': TestCore.run()` guard.
- `o/root/test.py`: prepares an isolated temporary application path, calls `o.start()`, imports `tester`, then calls `o.tester.run()`. It also contains local development-path setup.
- `o/root/tester.py`: test-only monkey-patches `o.Tester` with `_patch_registry`, `_patch_store`, `_patch_runtime`, and restoration methods. Many O tests call these methods. The state and LMDB lifecycle are not optional.
- `o/root/tests/test_dict.py`, `test_sync.py`: subclasses of `o.Tester`, existing direct class-level `run()` guards. Calling them in a standalone interpreter is not yet proof of correct setup.
- `web/root/test.py`: initializes `web.services.Server` then calls `web.tester.run()`.
- Existing workflows and docs call `python root/test.py` or reference `root/tests/`. O workflows also run selected tests through `o.tests.Test...run()` and launch explicit `root/tests/_test_performance_*.py` scripts. Web has Node/browser tests outside the Python native namespace.

Treat these as verified observations of the inspected branches, not a guarantee that future branches remain identical. Re-read current source before editing.

## 6. Implementation responsibilities

### A. Almasi `a.Tester`

Preserve:

- Existing test class model: subclasses of `a.Tester` with `@classmethod` test methods.
- Assertion semantics and exceptions: failures must propagate and produce nonzero process exit status.
- Existing readable headings, test names, passed indicators, and summary counts.
- Existing optional test-class-specific routines and cleanup where actually required.

Simplify:

- Replace namespace-based collection in `run_layer()` with iteration of the single fixed physical `tests/` directory, or remove `run_layer()` if its only purpose was iteration over library layers.
- Remove the ancestral library traversal from aggregate `run()`.
- Separate **one test class's execution** from **the current library's all-tests invocation** without implementing two runners.
- Compute display routes for moved files appropriately; eliminate route handling intended solely to reconstruct `a.tests.*` names if no longer necessary.
- Review `roots()` and `clean_fs()`: the current implementation iterates library roots and even overwrites its loop variable for both `__tmp__` and `tests_runtime`. Do not preserve inherited cleanup by accident. Clean only the test-owned locations required by the new contract, with correct lifecycle and no deletion of unrelated user files.

Import `a.Tester` itself through the existing public Almasi API. Use standard library `os` and `importlib` only if needed; avoid a new loader abstraction, registry, metaclass convention, or generic runner protocol.

### B. O — isolated initialization is the critical path

O's direct-run promise must hold in a fresh Python interpreter. The existing aggregate launcher prepares `o.start()` in a temporary application context; direct file execution currently goes straight to `TestClass.run()`, while test support lives in `root/tester.py` and patches `o.Tester`.

**Do not simply move the files and assume direct O tests are initialized.**

The O migration must provide **one shared O-specific test lifecycle** used by both aggregate and direct execution:

1. Construct the required temporary application/storage environment.
2. Initialize O in the correct order, once per run.
3. Make the existing test-specific LMDB/store isolation and patch/restore operations available to O test classes.
4. Restore/close state correctly even when tests fail.
5. Avoid touching a developer's persistent O store.

Prefer placing this mechanism with O's test support outside `root/` (for example, inside `tests/`), but validate imports in both entry modes before committing to a concrete file structure. The code need not become a production API. Choose a single explicit entry/lifecycle boundary, rather than doing setup in each of 30+ files or adding a second general test runner.

**Important unresolved design choice:** the current O test classes subclass `o.Tester` and call `TestClass.run()`. Determine the smallest way to make the O-specific lifecycle apply to those calls without invisible global monkey-patching on unrelated runtime imports. If preserving `o.Tester` is essential, document why and prove its initialization order. Otherwise an O-local test base class can be considered *only if* it removes more complexity than it adds and does not require unnecessary test rewrites. Do not assume a newly proposed API is already implemented.

### C. Web

Move Web native test files to `web/tests/`; preserve a single tests directory for Python, browser, and integration tests. Web's `tests.py` must retain required framework initialization (currently `web.services.Server.initialize()`) exactly once where appropriate. Individual `py tests/test_mcp.py` and other Web test files must likewise work independently; do not rely on setup having occurred via `tests.py`.

Continue running Node/Chromium E2E or integration tests using their existing specialized commands. Do not force non-Python tests through `a.Tester`. The common directory location is not a requirement for a common execution mechanism across languages.

Web PRs/branches may differ from the current default branch. Reconcile the migration with the active Web branch before touching files, and do not merge Web without explicit approval.

## 7. Test fixtures, paths, imports, and cleanup

Before moving files, inventory references to:

- `a.tests`, `o.tests`, `web.tests`;
- `root/tests/` and `root/test.py` in source, docs, scripts and GitHub Actions;
- relative fixture paths, `__file__` assumptions, `sys.path` mutations and imports of companion test modules;
- imported classes that relied on namespace plugin loading or auto-initialization;
- `root/tester.py`, `import tester`, and O temporary-store lifecycle;
- direct invocation guards and explicit benchmark scripts.

Migrate references to explicit ordinary test imports or paths. Preserve fixture bytes and test semantics. Avoid automatically importing arbitrary runtime modules as an indirect consequence of listing tests. Test resources must not become application/library resources merely to be locatable.

Do not silently add unsupported test extensions, a blanket global `sys.path` policy, magic names beyond the agreed `test_*.py` convention, or import-time test execution.

## 8. Migration sequence and verification

Implement in small cross-repository steps, with each boundary verifiable:

1. **Inventory baseline:** record all test files and scripts in all three repositories; record working pre-change aggregate/direct commands, existing CI steps, and known failures. Check the relevant code style and docs.
2. **Almasi:** alter `a.Tester` only as needed, move its tests and fixtures, create top-level `tests.py`, and remove `root/test.py`. Verify aggregate and direct tests; preserve reporting.
3. **O:** migrate test support out of runtime namespace, centralize initialization/isolation, move tests/fixtures/benchmarks, add `tests.py`. Verify first a direct isolated O file, then the full suite and explicit benchmarks; verify no persistent storage touched.
4. **Web:** reconcile active PR branch, migrate native tests into existing top-level `tests/`, create `tests.py`, update native initialization and preserve Node/Chromium/integration coverage.
5. **CI and docs:** change all invocations/paths in all affected repositories, including Python 3.11/3.12 workflow matrices and any explicit selected O tests or benchmarks.
6. **Diff review:** ensure no runtime behavior changed, no new dependency was introduced, no duplicate test folder remains, and the libraries no longer execute inherited test suites.

Suggested smoke checks from each repo root:

```bash
py tests.py
py tests/test_core.py         # Almasi example
py tests/test_dict.py         # O example (run in O repository)
py tests/test_mcp.py          # Web example (run in Web repository)
```

Run each command in the appropriate repository. Other representative tests should include fixture loading, failure exit status, O runtime isolation, and Web server/MCP initialization. Confirm no test suite of a parent library is launched by the consumer. Compare human-readable output to the current runner.

### Acceptance criteria

- [ ] Each repository has exactly one top-level `tests/` for tests and a top-level `tests.py` aggregate entry point.
- [ ] No `root/tests/`, `root/test.py`, or test-only `root/tester.py` remains in the runtime namespace.
- [ ] `py tests.py` runs every standard Python test of this repository, and **no** ancestor library's tests.
- [ ] `py tests/test_x.py` works directly in a clean process, including O and Web initialization.
- [ ] Test implementation remains ordinary `a.Tester` class methods; no pytest/unittest adoption, no second runner.
- [ ] O tests use one shared isolation mechanism, do not duplicate setup, and do not mutate persistent developer data.
- [ ] Existing fixtures, explicitly run benchmarks, browser tests, and integration tests remain accessible.
- [ ] Results and failures are reported at least as clearly as before; CI fails on a failing test.
- [ ] CI and documentation paths are updated consistently.
- [ ] All relevant test jobs pass; no unverified claim of integration or E2E coverage.

## 9. Non-goals and boundaries

This migration does **not** redesign the runtime module system, rewrite test assertions, replace the test runner with an external framework, add speculative per-method CLI selectors, or add a new generic plugin/fixture system.

Do not interpret `tests/` outside `root/` as evidence that dependencies cannot be used in tests. They can and must be tested through the consumer's own integration contracts, but dependency test suites are not executed automatically.

This note authorizes an implementation plan, **not an unconditional merge of future PRs**. In particular, keep Web unmerged until a separate decision.

## 10. Final design principle

**One library, one test suite, one top-level directory, one shared test execution mechanism.**

The aggregate runner and direct test files differ only in *selection*, not in test semantics or preparation. Test-specific setup is centralized; dependencies remain dependencies, not inherited suites. Every surviving mechanism must be necessary to satisfy these contracts.
