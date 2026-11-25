# Architecture: Git

`a.services.Git` is a Core Singleton service. No repository binding, initialization or
credential registry is needed for local checkout operations. The installer's
private `_Git` independently owns its own acquisition operations.
For remote GitHub operations, see [Git service API](git.md). The installed Git executable and its normal credentials/configuration
perform the actual operations. Callers select trusted repository URLs and local
working directories.

## Public API

- `clone(url: str, directory: str, timeout=None) -> str`: clone a Git URL
  (HTTPS, SSH, or local repository path) into a missing or empty destination.
  Git creates necessary parent directories. Return the supplied directory
  after success; existing nonempty destinations are rejected by Git.
  Reuse decisions belong to the caller.
- `get_repository_url(directory: str) -> str`: return the configured upstream remote URL.
- `await pull(directory: str, *, exact=False, timeout=None) -> str`: update the
  specified checkout and return its final HEAD. By default use `--ff-only`;
  do not merge divergent histories or discard changes. Explicit `exact=True`
  matches upstream HEAD even after rewinds, rejects dirty tracked files and
  is intended only for dedicated deployment checkouts. Git reset --hard can
  remove untracked files that obstruct tracked paths. Use an exact checkout root.
- `is_repository(directory: str) -> bool`: recognize a working checkout root
  with a valid .git directory or gitfile, including linked worktrees.
  Return False for missing directories, ordinary directories, subdirectories
  of another checkout and invalid .git markers. Bare repositories are not
  working checkouts and are outside this predicate's scope.

Clone blocks; pull is asynchronous and cancels its active Git subprocess
on cancellation. Optional timeout is in seconds per network command,
with None meaning no explicit timeout. Git command failures propagate as
subprocess.CalledProcessError (with captured stdout/stderr), subprocess.TimeoutExpired (clone), asyncio.TimeoutError (pull),
or OSError for execution failures. The predicate returns False for an invalid
checkout; failure to start Git still propagates. Operations use argument
vectors, not a shell. Callers must not supply untrusted repository locations
for execution or assume Git acquisition establishes trust.

```python
from almasi import a

git = a.services.Git

if not git.is_repository(directory):
	git.clone(url, directory)
else:
	await git.pull(directory)
```

The installer owns library acquisition, caching, dependency installation and
offline fallback independently of Core. Hub uses the Core Git service for
its own workspaces and repository creation.
Git owns no repository inventory or process supervision. Concurrent pulls of the same checkout in one event loop are serialized;
other mutations and separate processes must be coordinated by callers.

Automated Git and GitHub CLI commands disable client-side hooks and terminal
prompts through their subprocess environment. Git children inherit that setting;
manual Git commands and persistent configuration remain unchanged.
