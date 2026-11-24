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

import os
import re
import subprocess
import tempfile

from almasi import a


class Git(a.Singleton):

	_HOST = 'github.com'

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Execute Git directly, preserving diagnostics and native failure types.
	# ----------------------------------------------------------------------
	def _run(
		self,
		arguments,
		timeout = None,
		check   = True
	):
		return subprocess.run(
			['git', *arguments],
			capture_output = True,
			text           = True,
			timeout        = timeout,
			check          = check
		)

	# Validate an explicit GitHub owner/name, never a URL or shell option.
	# ----------------------------------------------------------------------
	def _validate_repository(self, repo):
		is_valid = (
			isinstance(repo, str)
			and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+', repo)
			and repo.rsplit('/', 1)[1] not in ('.', '..')
		)

		if is_valid:
			result = repo
		else:
			raise ValueError(f'Expected GitHub owner/name: {repo!r}')

		return result

	# Use the authenticated GitHub CLI without interactive prompts.
	# ----------------------------------------------------------------------
	def _gh(self, arguments, check=True):
		environment = dict(os.environ, GH_HOST=self._HOST, GH_PROMPT_DISABLED='1')

		return subprocess.run(
			['gh', *arguments],
			env            = environment,
			capture_output = True,
			text           = True,
			check          = check
		)

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Clone a trusted remote into an explicitly selected local directory.
	# ----------------------------------------------------------------------
	def clone(self, url: str, directory: str, timeout: float | None = None) -> str:
		self._run(['clone', '--quiet', '--', url, directory], timeout=timeout)

		return directory

	# Update this checkout without merging or implicitly using a parent repo.
	# ----------------------------------------------------------------------
	def pull(self, directory: str, timeout: float | None = None) -> None:
		self._run(
			['-C', directory, '--git-dir=.git', '--work-tree=.', 'pull', '--ff-only', '--quiet'],
			timeout=timeout
		)

	# Recognize working checkout roots, including linked Git worktrees.
	# ----------------------------------------------------------------------
	def is_repository(self, directory: str) -> bool:
		result = False

		if os.path.exists(os.path.join(directory, '.git')):
			probe = self._run(
				['-C', directory, '--git-dir=.git', '--work-tree=.', 'rev-parse', '--is-inside-work-tree'],
				check=False
			)
			result = probe.returncode == 0 and probe.stdout.strip() == 'true'

		return result

	# Check repository visibility to the authenticated GitHub identity.
	# ----------------------------------------------------------------------
	def exists(self, repo: str) -> bool:
		repo  = self._validate_repository(repo)
		probe = self._gh(['api', '--hostname', self._HOST, '--include', f'repos/{repo}'], check=False)

		if probe.returncode == 0:
			result = True
		elif re.match(r'HTTP/\S+ 404\b', probe.stdout):
			result = False
		else:
			raise RuntimeError(f'GitHub lookup failed for {repo}: {probe.stderr.strip()}')

		return result

	# Create an independent repository, optionally with the source branch.
	# ----------------------------------------------------------------------
	def create(
		self,
		new_repo  : str,
		from_repo : str | None = None,
		private   : bool       = True
	) -> str:
		new_repo   = self._validate_repository(new_repo)
		visibility = '--private' if private else '--public'
		arguments  = ['repo', 'create', new_repo, visibility]

		if from_repo is None:
			self._gh(arguments)
		else:
			from_repo = self._validate_repository(from_repo)

			with tempfile.TemporaryDirectory(prefix='almasi_git_') as directory:
				self.clone(f'https://{self._HOST}/{from_repo}.git', directory)
				self._gh([*arguments, '--source', directory, '--remote', 'destination', '--push'])

		return f'https://{self._HOST}/{new_repo}.git'
