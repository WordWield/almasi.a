# Git service

`a.services.Git` is a Singleton ready to use without initialization.
Remote repositories are identified by two separate strings, `owner` and
`name`, on github.com. A local checkout is identified by its filesystem
`path`. The service derives Git URLs internally. The installer's private
Git implementation is independent.

```python
from almasi import a

git = a.services.Git

if not git.exists_remote('owner', 'project'):
	git.create_remote('owner', 'project', from_owner='base', from_name='starter')

if not git.is_cloned('./project'):
	git.clone('owner', 'project', './project')
else:
	await git.pull('./project')
```

## Remote operations

- `list_remotes(owner: str) -> list[str]`: list all repository names
  visible under the specified GitHub owner, including accessible private
  repositories. Reads all pages; no checkout or remote mutation.
- `exists_remote(owner: str, name: str) -> bool`: True means the remote is
  visible; False means GitHub returned HTTP 404, which can also indicate
  insufficient visibility. Other failures propagate.
- `create_remote(owner, name, from_owner=None, from_name=None, private=True) -> None`:
  create an empty repository when both source coordinates are omitted.
  When both are supplied, clone the source's default branch into a temporary
  checkout and push its history to the new independent repository, including
  across owners. Supplying just one source coordinate is invalid.
  No GitHub template or fork is required; the source is not modified.
  Explicit private=False requests public visibility. If the initial push
  fails after creation, inspect the destination before retrying.
- `delete_remote(owner: str, name: str) -> None`: permanently delete the
  selected repository, without an interactive confirmation, retry or
  local deletion. Requires administration permission (or classic token
  delete_repo scope). All failures, including 404, propagate.
- `rename_remote(owner: str, name: str, new_name: str) -> None`: rename
  within the same owner, preserving the repository and its Git history.
  Local checkouts are not moved or modified.

## Local checkout operations

- `clone(owner, name, path, timeout=None) -> str`: clone the GitHub
  repository over HTTPS into a missing or empty path and return that path.
  The caller determines whether to reuse an existing checkout.
- `is_cloned(path: str) -> bool`: recognize an exact working checkout
  root, including one created by git init or a linked worktree.
- `await pull(path, *, exact=False, timeout=None) -> str`: return the final
  commit SHA. Default is fast-forward only. With exact=True, match upstream
  HEAD including rewinds, rejecting dirty tracked files. Use exact mode
  only for dedicated deployment checkouts.
- `get_remote(path: str) -> tuple[str, str]`: return (owner, name) from the
  current branch's configured GitHub upstream (HTTPS or standard SSH).
  Requires an exact checkout root and a configured upstream. Unsupported
  hosts and local repository paths raise ValueError.
- `set_remote(path: str, owner: str, name: str) -> None`: update that
  upstream remote's fetch URL to the specified GitHub repository, preserving
  branch tracking and working files. Explicit push URLs are unchanged.
  Does not contact the remote.

For an authorized coordinated rename:

```python
git.rename_remote('owner', 'old', 'new')
git.set_remote(path, 'owner', 'new')
```

The caller owns target authorization, coordination of local and remote
mutations, and recovery from partial failure. GitHub CLI (`gh`) and
appropriate Git credentials must be configured before remote operations.
Creation from a source requires read access to the source and create/push
access to the destination. Rename and deletion require administration
permission. No credential registry is introduced.

Core Git commands disable client-side hooks and terminal prompts for their
subprocesses, including Git children started by gh. Normal manual commands,
persistent configuration and server-side checks are unchanged. Failed
checked commands preserve CalledProcessError and attach captured diagnostics.
See [Git architecture](architecture.git.md) for lifecycle details.
