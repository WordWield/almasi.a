# Git service

`a.services.Git` provides Git checkout operations and authenticated GitHub
repository management. It is a stateless Almasi Singleton service, ready to use
without explicit initialization. Core is independent of the installer's
private Git implementation.

```python
from almasi import a

git = a.services.Git

if not git.exists('owner/project'):
	git.create('owner/project', from_repo='owner/starter')

git.clone('https://github.com/owner/project.git', './project')
```

- `exists(repo: str) -> bool`: accepts an explicit GitHub `owner/name`.
  True means the repository is visible to the authenticated identity. False
  means GitHub returned HTTP 404; GitHub also uses 404 for inaccessible private
  repositories. Other HTTP errors, connection failures and missing CLI raise
  errors. Never interpret False as proof of permission to create.
- `create(new_repo: str, from_repo: str | None = None, private: bool = True) -> str`:
  creates a new empty repository, or clones the source's default branch into
  a temporary checkout and pushes it (including its commit history) to a new,
  independent repository. Returns its HTTPS clone URL. It does not modify the
  source, require a GitHub template, or overwrite an existing destination.
  Explicit `private=False` requests public visibility; only use this for code
  authorized for public release. If creation succeeds but the push fails, the
  destination may remain empty and must be inspected before retrying.
- `clone(url, directory, timeout=None)`, `pull(directory, timeout=None)`,
  `is_repository(directory)`: local checkout operations implemented by Core; Git errors
  propagate. clone returns the directory, pull returns None, and
  is_repository returns a boolean.

Remote operations require GitHub CLI (`gh`) authenticated to github.com,
permission to create repositories under the target owner, and Git credentials
to read the source and push the destination. Configure these before use,
for example with `gh auth login --hostname github.com` and
`gh auth setup-git --hostname github.com`. No new Python dependency is required.

Core Git commands disable client-side Git hooks and terminal prompts for their
subprocesses, including Git children started by `gh`. Normal manual Git commands,
user configuration and server-side repository checks are unchanged.
