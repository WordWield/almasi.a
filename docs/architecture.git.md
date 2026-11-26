# Architecture: Git

`a.services.Git` is a Core Singleton service. No repository binding,
initialization or credential registry is needed. It owns GitHub repository
identity and URL construction, Git command execution and local checkout
recognition. The installed Git and GitHub CLI executables provide the actual
operations and authentication.

The [Git service API](git.md) defines remote operations in owner/name
coordinates and local operations in filesystem paths. URLs are internal.
The installer's private Git implementation independently owns library
acquisition and is not part of this contract.

## Local lifecycle

- Clone derives the HTTPS address of the GitHub repository and returns the
  selected checkout path. Git creates necessary parent directories. Existing
  nonempty destinations are rejected by Git; reuse is the caller's decision.
- is_cloned recognizes an exact working checkout root, including a valid
  .git directory or gitfile. Missing paths, ordinary directories, nested
  subdirectories, invalid .git markers and bare repositories return False.
- get_remote and set_remote resolve the current branch's configured upstream.
  get_remote returns its GitHub (owner, name), not a URL. set_remote preserves
  branch tracking and explicitly configured push URLs.
- Pull defaults to fast-forward-only. exact=True matches upstream HEAD,
  including rewinds, and rejects dirty tracked files. Git reset --hard can
  remove untracked files that obstruct tracked paths; exact mode is intended
  only for dedicated deployment checkouts.

Clone blocks; pull is asynchronous and cancels its active Git subprocess on
cancellation. Timeout is in seconds per network command; None means no explicit
timeout. Git failures propagate as subprocess.CalledProcessError with captured
diagnostics, subprocess.TimeoutExpired (clone), asyncio.TimeoutError (pull),
or OSError for execution failures. Operations use argument vectors, not shells.

## Responsibility boundaries

The caller selects authorized repositories and paths, and coordinates remote
rename/deletion with local state. Git owns no project inventory, authorization
policy, or process supervision. Concurrent pulls of one checkout in one
event loop are serialized; other mutations and separate processes must be
coordinated by callers.

Optional per-operation tokens override authentication in the child process
only; the service stores no credentials. GitHub HTTPS uses a process-local
credential helper override, while gh receives GH_TOKEN. Source acquisition
in create_remote uses ordinary authentication; the token applies to the
destination. See the API documentation for exact contracts.

Automated commands disable client-side hooks and terminal prompts through
their subprocess environment. Git children inherit that setting; manual
commands and persistent configuration remain unchanged.
