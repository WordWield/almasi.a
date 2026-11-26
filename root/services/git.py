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
	def _checkout(self, directory):
		path = os.path.realpath(directory)

		if self.is_repository(path):
			result = ['git', '-C', path, '--git-dir=.git', '--work-tree=.']
		else:
			raise ValueError(f'Expected a Git working checkout root: {directory}')

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
	def _pull_lock(self, directory):
		lock = self._pull_locks.get(directory)

		if lock is None:
			lock = asyncio.Lock()
			self._pull_locks[directory] = lock

		return lock

	# Validate an explicit GitHub owner/name, never a URL or shell option.
	# ----------------------------------------------------------------------
	def _validate_repository(self, repository):
		is_valid = (
			isinstance(repository, str)
			and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+', repository)
			and repository.rsplit('/', 1)[1] not in ('.', '..')
		)

		if is_valid:
			result = repository
		else:
			raise ValueError(f'Expected GitHub owner/name: {repository!r}')

		return result

	# Use the authenticated GitHub CLI without interactive prompts.
	# ----------------------------------------------------------------------
	def _gh(self, arguments, check=True):
		return self._run(['gh', *arguments], check=check)

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Clone a trusted remote into an explicitly selected local directory.
	# ----------------------------------------------------------------------
	def clone(self, url: str, directory: str, timeout: float | None = None) -> str:
		self._run(['git', 'clone', '--quiet', '--', url, directory], timeout=timeout)

		return directory

	# Return the remote URL selected by the checkout's tracking configuration.
	# ----------------------------------------------------------------------
	def get_repository_url(self, directory: str) -> str:
		'''Return the configured upstream remote URL of an exact checkout root.'''
		command   = self._checkout(directory)
		_, remote = self._upstream(command)

		return self._run([*command, 'remote', 'get-url', remote]).stdout.strip()

	# Change the URL of the remote selected by the checkout's tracking configuration.
	# ----------------------------------------------------------------------
	def set_repository_url(self, directory: str, url: str):
		'''Set the upstream remote fetch URL without changing the branch or files.
		An explicitly configured push URL is not changed.'''
		command   = self._checkout(directory)
		_, remote = self._upstream(command)

		self._run([*command, 'remote', 'set-url', '--', remote, url])

	# Update one checkout using the requested upstream synchronization policy.
	# ----------------------------------------------------------------------
	async def pull(
		self,
		directory : str,
		*,
		exact     : bool         = False,
		timeout   : float | None = None
	) -> str:
		'''Fetch and update the selected checkout, returning its final HEAD.
		By default allow only fast-forward updates. exact=True matches upstream
		HEAD, including rewinds, and rejects uncommitted tracked changes.
		Timeout is in seconds per network command; cancellation stops that
		command. Use exact mode only for dedicated deployment checkouts.'''
		command = self._checkout(directory)

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
	def is_repository(self, directory: str) -> bool:
		result = False

		if os.path.exists(os.path.join(directory, '.git')):
			probe = self._run(
				['git', '-C', directory, '--git-dir=.git', '--work-tree=.', 'rev-parse', '--is-inside-work-tree'],
				check=False
			)
			result = probe.returncode == 0 and probe.stdout.strip() == 'true'

		return result

	# List all repositories visible to the authenticated identity under one owner.
	# ----------------------------------------------------------------------
	def list_repositories(self, owner: str) -> list[str]:
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
	def exists(self, repository: str) -> bool:
		repository = self._validate_repository(repository)
		probe      = self._gh(['api', '--hostname', self._HOST, '--include', f'repos/{repository}'], check=False)

		if probe.returncode == 0:
			result = True
		elif re.match(r'HTTP/\S+ 404\b', probe.stdout):
			result = False
		else:
			raise RuntimeError(f'GitHub lookup failed for {repository}: {probe.stderr.strip()}')

		return result

	# Create an independent repository, optionally with the source branch.
	# ----------------------------------------------------------------------
	def create(
		self,
		new_repository  : str,
		from_repository : str | None = None,
		private         : bool       = True
	) -> str:
		new_repository   = self._validate_repository(new_repository)
		visibility     = '--private' if private else '--public'
		arguments      = ['repo', 'create', new_repository, visibility]

		if from_repository is None:
			self._gh(arguments)
		else:
			from_repository = self._validate_repository(from_repository)

			with tempfile.TemporaryDirectory(prefix='almasi_git_') as directory:
				self.clone(f'https://{self._HOST}/{from_repository}.git', directory)
				self._gh([*arguments, '--source', directory, '--remote', 'destination', '--push'])

		return f'https://{self._HOST}/{new_repository}.git'

	# Delete exactly one explicitly named remote repository.
	# ----------------------------------------------------------------------
	def delete(self, repository: str):
		'''Permanently delete a GitHub owner/name using the active credential.
		Requires repository administration permission; errors propagate.'''
		repository = self._validate_repository(repository)
		self._gh(['api', '--hostname', self._HOST, '--method', 'DELETE', f'repos/{repository}'])

	# Rename a repository in place, preserving its identity and history.
	# ----------------------------------------------------------------------
	def rename(self, repository: str, new_name: str) -> str:
		'''Rename a GitHub owner/name within its current owner.
		Return the new HTTPS clone URL; local checkouts are unchanged.'''
		repository = self._validate_repository(repository)
		owner      = repository.split('/')[0]

		if isinstance(new_name, str) and '/' not in new_name:
			destination = self._validate_repository(f'{owner}/{new_name}')
			self._gh(['api', '--hostname', self._HOST, '--method', 'PATCH', f'repos/{repository}', '-f', f'name={new_name}'])
		else:
			raise ValueError(f'Expected a repository name: {new_name!r}')

		return f'https://{self._HOST}/{destination}.git'
