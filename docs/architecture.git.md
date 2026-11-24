# Architecture: Git

`almasi.services.Git` is a stateless, lazily resolved Core singleton.
No initialization, GitHub API, library naming convention or credential registry
is needed. The installed Git executable and its normal credentials/configuration
perform the actual operations. Callers select trusted repository URLs and local
working directories.

## Public API

- `clone(url: str, directory: str, timeout=None) -> str`: clone a Git URL
  (HTTPS, SSH, or local repository path) into a missing or empty destination.
  Git creates necessary parent directories. Return the supplied directory
  after success; existing nonempty destinations are rejected by Git.
  Reuse decisions belong to the caller.
- `pull(directory: str, timeout=None) -> None`: update the specified working
  checkout using its configured upstream, with `--ff-only`. Do not create
  a merge commit, reset changes, rebase divergent history or update a
  containing repository by accident.
- `is_repository(directory: str) -> bool`: recognize a working checkout root
  with a valid .git directory or gitfile, including linked worktrees.
  Return False for missing directories, ordinary directories, subdirectories
  of another checkout and invalid .git markers. Bare repositories are not
  working checkouts and are outside this predicate's scope.

Clone and pull block until Git completes. Optional timeout is in seconds,
with None meaning no explicit timeout. Git command failures propagate as
subprocess.CalledProcessError (with captured stdout/stderr), subprocess.TimeoutExpired,
or OSError for execution failures. The predicate returns False for an invalid
checkout; failure to start Git still propagates. Operations use argument
vectors, not a shell. Callers must not supply untrusted repository locations
for execution or assume Git acquisition establishes trust.

```python
import almasi

git = almasi.services.Git

if not git.is_repository(directory):
	git.clone(url, directory)
else:
	git.pull(directory)
```

Libraries retains its existing naming, shared cache, dependency installation,
progress and offline fallback policies; it delegates Git operations to this
service. Hub can use the same operations for its own independent workspaces.
Git owns no repository inventory or process supervision. Concurrent mutations
to the same checkout must be coordinated by callers.
