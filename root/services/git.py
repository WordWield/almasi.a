# ==============================================================================
# GIT SERVICE
# ==============================================================================
# PURPOSE:
# Provide local Git and remote GitHub operations to Almasi libraries.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Local checkout and remote GitHub repository operations.
# Delegates: Git execution and authentication to Git and GitHub CLI.
# ==============================================================================

import asyncio
import os
import re
import subprocess
import tempfile
from weakref import WeakValueDictionary

from almasi import a


class Git(a.Singleton):

	_HOST       = 'github.com'
	_pull_locks = WeakValueDictionary()

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Share noninteractive, hook-free configuration across all CLI operations.
	# ----------------------------------------------------------------------
	def _environment(self):
		environment = dict(
			os.environ,
			GH_HOST             = self._HOST,
			GH_PROMPT_DISABLED  = '1',
			GIT_TERMINAL_PROMPT = '0'
		)

		index = int(environment.get('GIT_CONFIG_COUNT', '0'))
		environment[f'GIT_CONFIG_KEY_{index}']   = 'core.hooksPath'
		environment[f'GIT_CONFIG_VALUE_{index}'] = os.devnull
		environment['GIT_CONFIG_COUNT']         = str(index + 1)

		return environment

	# Preserve native failures and their captured diagnostics.
	# ----------------------------------------------------------------------
	def _annotate_error(self, error):
		for output in (error.stdout, error.stderr):
			if output and output.strip():
				error.add_note(output.strip())

	# Execute short local and synchronous remote operations without a shell.
	# ----------------------------------------------------------------------
	def _run(
		self,
		arguments,
		timeout = None,
		check   = True
	):
		try:
			result = subprocess.run(
				arguments,
				env            = self._environment(),
				capture_output = True,
				text           = True,
				timeout        = timeout,
				check          = check
			)
		except subprocess.CalledProcessError as error:
			self._annotate_error(error)
			raise

		return result

	# Await a Git operation without blocking the caller's event loop.
	# ----------------------------------------------------------------------
	async def _run_async(self, arguments, timeout=None):
		process = await asyncio.create_subprocess_exec(
			*arguments,
			env    = self._environment(),
			stdout = asyncio.subprocess.PIPE,
			stderr = asyncio.subprocess.PIPE
		)

		try:
			stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
		except (asyncio.CancelledError, asyncio.TimeoutError):
			if process.returncode is None:
				process.kill()

			await process.communicate()
			raise

		if process.returncode == 0:
			result = stdout.decode('utf-8', errors='replace').strip()
		else:
			error = subprocess.CalledProcessError(
				process.returncode, arguments,
				output = stdout.decode('utf-8', errors='replace'),
				stderr = stderr.decode('utf-8', errors='replace')
			)
			self._annotate_error(error)
			raise error

		return result

	# Require the selected working tree itself, never a containing repository.
	# ----------------------------------------------------------------------
	def _checkout(self, path):
		path = os.path.realpath(path)

		if self.is_cloned(path):
			result = ['git', '-C', path, '--git-dir=.git', '--work-tree=.']
		else:
			raise ValueError(f'Expected a Git working checkout root: {path}')

		return result

	# Resolve the configured upstream and its remote on each operation.
	# ----------------------------------------------------------------------
	def _upstream(self, command):
		upstream = self._run([*command, 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}']).stdout.strip()
		branch   = self._run([*command, 'symbolic-ref', '--short', 'HEAD']).stdout.strip()
		remote   = self._run([*command, 'config', '--get', f'branch.{branch}.remote']).stdout.strip()

		return upstream, remote

	# Serialize concurrent updates to one working tree, not unrelated trees.
	# ----------------------------------------------------------------------
	def _pull_lock(self, path):
		lock = self._pull_locks.get(path)

		if lock is None:
			lock = asyncio.Lock()
			self._pull_locks[path] = lock

		return lock

	# Validate the two coordinates before forming a GitHub repository slug.
	# ----------------------------------------------------------------------
	def _get_slug(self, owner, name):
		is_valid = (
			isinstance(owner, str)
			and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*', owner)
			and isinstance(name, str)
			and re.fullmatch(r'[A-Za-z0-9_.-]+', name)
			and name not in ('.', '..')
		)

		if is_valid:
			result = f'{owner}/{name}'
		else:
			raise ValueError(f'Expected GitHub owner and name: {owner!r}, {name!r}')

		return result

	# Derive the canonical HTTPS address from repository identity.
	# ----------------------------------------------------------------------
	def _get_url(self, owner, name):
		return f'https://{self._HOST}/{self._get_slug(owner, name)}.git'

	# Use the authenticated GitHub CLI without interactive prompts.
	# ----------------------------------------------------------------------
	def _gh(self, arguments, check=True):
		return self._run(['gh', *arguments], check=check)

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Clone an explicitly named GitHub repository into the selected path.
	# ----------------------------------------------------------------------
	def clone(self, owner: str, name: str, path: str, timeout: float | None = None) -> str:
		url = self._get_url(owner, name)
		self._run(['git', 'clone', '--quiet', '--', url, path], timeout=timeout)

		return path

	# Resolve the GitHub identity of the checkout's configured upstream.
	# ----------------------------------------------------------------------
	def get_remote(self, path: str) -> tuple[str, str]:
		'''Return (owner, name) for a configured GitHub HTTPS or SSH upstream.'''
		command   = self._checkout(path)
		_, remote = self._upstream(command)
		url       = self._run([*command, 'config', '--get', f'remote.{remote}.url']).stdout.strip()
		host      = re.escape(self._HOST)
		match     = re.fullmatch(rf'(?:https://{host}/|ssh://git@{host}/|git@{host}:)([^/]+)/([^/]+)', url)

		if match is not None:
			owner, name = match.groups()
			name        = name.removesuffix('.git')
			self._get_slug(owner, name)
		else:
			raise ValueError('Expected a GitHub upstream remote')

		return owner, name

	# Update the configured upstream without changing branch or checkout contents.
	# ----------------------------------------------------------------------
	def set_remote(self, path: str, owner: str, name: str) -> None:
		'''Set the upstream fetch URL to the selected GitHub repository.
		An explicitly configured push URL is not changed.'''
		url       = self._get_url(owner, name)
		command   = self._checkout(path)
		_, remote = self._upstream(command)

		self._run([*command, 'remote', 'set-url', '--', remote, url])

	# Update one checkout using the requested upstream synchronization policy.
	# ----------------------------------------------------------------------
	async def pull(
		self,
		path : str,
		*,
		exact     : bool         = False,
		timeout   : float | None = None
	) -> str:
		'''Fetch and update the selected checkout, returning its final HEAD.
		By default allow only fast-forward updates. exact=True matches upstream
		HEAD, including rewinds, and rejects uncommitted tracked changes.
		Timeout is in seconds per network command; cancellation stops that
		command. Use exact mode only for dedicated deployment checkouts.'''
		command = self._checkout(path)

		async with self._pull_lock(command[2]):
			if exact:
				if not self._run([*command, 'status', '--porcelain', '--untracked-files=no']).stdout.strip():
					upstream, remote = self._upstream(command)
					await self._run_async([*command, 'fetch', '--quiet', '--no-tags', remote], timeout=timeout)

					if not self._run([*command, 'status', '--porcelain', '--untracked-files=no']).stdout.strip():
						commit  = self._run([*command, 'rev-parse', '--verify', upstream + '^{commit}']).stdout.strip()
						current = self._run([*command, 'rev-parse', 'HEAD']).stdout.strip()

						if current != commit:
							self._run([*command, 'reset', '--hard', '--quiet', commit])
					else:
						raise RuntimeError('Uncommitted tracked files prevent Git synchronization')
				else:
					raise RuntimeError('Uncommitted tracked files prevent Git synchronization')
			else:
				await self._run_async([*command, 'pull', '--ff-only', '--quiet'], timeout=timeout)

			result = self._run([*command, 'rev-parse', 'HEAD']).stdout.strip()

		return result

	# Recognize working checkout roots, including linked Git worktrees.
	# ----------------------------------------------------------------------
	def is_cloned(self, path: str) -> bool:
		result = False

		if os.path.exists(os.path.join(path, '.git')):
			probe = self._run(
				['git', '-C', path, '--git-dir=.git', '--work-tree=.', 'rev-parse', '--is-inside-work-tree'],
				check=False
			)
			result = probe.returncode == 0 and probe.stdout.strip() == 'true'

		return result

	# List all repositories visible to the authenticated identity under one owner.
	# ----------------------------------------------------------------------
	def list_remotes(self, owner: str) -> list[str]:
		if isinstance(owner, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*', owner):
			query = '''query($owner: String!, $endCursor: String) {
				repositoryOwner(login: $owner) {
					repositories(first: 100, after: $endCursor, ownerAffiliations: OWNER) {
						nodes { name }
						pageInfo { hasNextPage endCursor }
					}
				}
			}'''
			response = self._gh([
				'api', 'graphql', '--hostname', self._HOST, '--paginate',
				'-f', f'query={query}', '-f', f'owner={owner}',
				'--jq', '.data.repositoryOwner.repositories.nodes[].name'
			])
			result = response.stdout.splitlines()
		else:
			raise ValueError(f'Expected GitHub owner: {owner!r}')

		return result

	# Check repository visibility to the authenticated GitHub identity.
	# ----------------------------------------------------------------------
	def exists_remote(self, owner: str, name: str) -> bool:
		slug  = self._get_slug(owner, name)
		probe = self._gh(['api', '--hostname', self._HOST, '--include', f'repos/{slug}'], check=False)

		if probe.returncode == 0:
			result = True
		elif re.match(r'HTTP/\S+ 404\b', probe.stdout):
			result = False
		else:
			raise RuntimeError(f'GitHub lookup failed for {slug}: {probe.stderr.strip()}')

		return result

	# Create an independent repository, optionally with the source branch.
	# ----------------------------------------------------------------------
	def create_remote(
		self,
		owner      : str,
		name       : str,
		from_owner : str | None = None,
		from_name  : str | None = None,
		private    : bool       = True
	) -> None:
		slug       = self._get_slug(owner, name)
		visibility = '--private' if private else '--public'
		arguments  = ['repo', 'create', slug, visibility]

		if from_owner is None and from_name is None:
			self._gh(arguments)
		elif from_owner is not None and from_name is not None:
			with tempfile.TemporaryDirectory(prefix='almasi_git_') as path:
				self.clone(from_owner, from_name, path)
				self._gh([*arguments, '--source', path, '--remote', 'destination', '--push'])
		else:
			raise ValueError('Source owner and name must be supplied together')

	# Delete exactly one explicitly named remote repository.
	# ----------------------------------------------------------------------
	def delete_remote(self, owner: str, name: str) -> None:
		'''Permanently delete the selected GitHub repository.'''
		slug = self._get_slug(owner, name)
		self._gh(['api', '--hostname', self._HOST, '--method', 'DELETE', f'repos/{slug}'])

	# Rename a repository within its existing owner, preserving its history.
	# ----------------------------------------------------------------------
	def rename_remote(self, owner: str, name: str, new_name: str) -> None:
		'''Rename the remote repository; local checkouts are unchanged.'''
		slug = self._get_slug(owner, name)
		self._get_slug(owner, new_name)
		self._gh(['api', '--hostname', self._HOST, '--method', 'PATCH', f'repos/{slug}', '-f', f'name={new_name}'])
