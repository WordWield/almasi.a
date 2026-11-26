# Git service

`a.services.Git` provides Git checkout operations and authenticated GitHub
repository management. It is an Almasi Singleton service without repository binding, ready to use
without explicit initialization. Core is independent of the installer's
private Git implementation.

```python
from almasi import a

git = a.services.Git

if not git.exists('owner/project'):
	git.create('owner/project', from_repository='owner/starter')

git.clone('https://github.com/owner/project.git', './project')
```

- `list_repositories(owner: str) -> list[str]`: lists repository names (not
  owner/name pairs) visible to the authenticated GitHub identity under the
  specified owner, including accessible private repositories. Reads all pages
  via GitHub CLI; discovery does not clone or create repositories. Invalid owners
  and CLI failures raise errors.
- `exists(repository: str) -> bool`: accepts an explicit GitHub `owner/name`.
  True means the repository is visible to the authenticated identity. False
  means GitHub returned HTTP 404; GitHub also uses 404 for inaccessible private
  repositories. Other HTTP errors, connection failures and missing CLI raise
  errors. Never interpret False as proof of permission to create.
- `create(new_repository: str, from_repository: str | None = None, private: bool = True) -> str`:
  creates a new empty repository, or clones the source's default branch into
  a temporary checkout and pushes it (including its commit history) to a new,
  independent repository. Returns its HTTPS clone URL. It does not modify the
  source, require a GitHub template, or overwrite an existing destination.
  Explicit `private=False` requests public visibility; only use this for code
  authorized for public release. If creation succeeds but the push fails, the
  destination may remain empty and must be inspected before retrying.
- `delete(repository: str) -> None`: permanently deletes the explicit GitHub
  owner/name through the authenticated API. Requires administration write
  permission (or the classic token's delete_repo scope). No confirmation
  prompt, local deletion, automatic retry or ignored 404. The caller must
  authorize the target and coordinate its lifecycle before calling.
- `rename(repository: str, new_name: str) -> str`: renames the existing remote
  repository within its current owner, preserving repository identity and Git
  history. Accepts an owner/name and a bare destination name, not a new owner.
  Returns the new HTTPS clone URL. Does not move local checkouts or change
  their Git configuration. Provider failures propagate.
- `set_repository_url(directory: str, url: str) -> None`: changes the fetch
  URL of the remote selected by the checkout's current upstream configuration.
  Requires an exact checkout root and a configured upstream. Does not contact
  the remote, change the working tree or alter explicitly configured push URLs.
- `clone(url, directory, timeout=None) -> str`: clone and return the directory.
- `get_repository_url(directory) -> str`: return the checkout's upstream remote URL.
- `await pull(directory, *, exact=False, timeout=None) -> str`: return the final
  commit SHA after a fast-forward-only update, or explicitly synchronize to
  upstream HEAD (including rewinds) with exact=True; reject dirty tracked
  files in exact mode. Only use exact mode on dedicated deployment checkouts.
- `is_repository(directory) -> bool`: recognize an exact working checkout root.
  See [Git architecture](architecture.git.md) for lifecycle and error contracts.

For a coordinated, authorized rename, for example:

```python
url = git.rename('owner/old', 'new')
git.set_repository_url(directory, url)
```

Remote operations require GitHub CLI (`gh`) authenticated to github.com,
permission to create repositories under the target owner, and Git credentials
to read the source and push the destination. Configure these before use,
for example with `gh auth login --hostname github.com` and
`gh auth setup-git --hostname github.com`. No new Python dependency is required.

Core Git commands disable client-side Git hooks and terminal prompts for their
subprocesses, including Git children started by `gh`. Normal manual Git commands,
user configuration and server-side repository checks are unchanged.

Failed checked commands retain their native CalledProcessError and attach
captured stdout and stderr as exception notes, visible in the traceback.
