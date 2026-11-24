# ==============================================================================
# GIT SERVICE
# ==============================================================================
# PURPOSE:
# Provide reusable Git checkout operations to Almasi libraries.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Remote GitHub repository existence and creation.
# Delegates: Local checkout operations to the installer's implementation.
# Delegates: Remote authentication and creation to GitHub CLI.
# ==============================================================================

import os
import re
import subprocess
import tempfile

from almasi import a, _git


_Git = getattr(_git, '_Git', None) or _git.Git


class Git(_Git, a.Module):

	_HOST = 'github.com'

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Validate an explicit GitHub owner/name, never a URL or shell option.
	# ----------------------------------------------------------------------
	@staticmethod
	def _validate_repository(repo):
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
	@classmethod
	def _gh(cls, arguments, check=True):
		environment = dict(os.environ, GH_HOST=cls._HOST, GH_PROMPT_DISABLED='1')

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

	# Check repository visibility to the authenticated GitHub identity.
	# ----------------------------------------------------------------------
	@classmethod
	def exists(cls, repo: str) -> bool:
		repo  = cls._validate_repository(repo)
		probe = cls._gh(['api', '--hostname', cls._HOST, '--include', f'repos/{repo}'], check=False)

		if probe.returncode == 0:
			result = True
		elif re.match(r'HTTP/\S+ 404\b', probe.stdout):
			result = False
		else:
			raise RuntimeError(f'GitHub lookup failed for {repo}: {probe.stderr.strip()}')

		return result

	# Create an independent repository, optionally with the source branch.
	# ----------------------------------------------------------------------
	@classmethod
	def create(
		cls,
		new_repo  : str,
		from_repo : str | None = None,
		private   : bool       = True
	) -> str:
		new_repo   = cls._validate_repository(new_repo)
		visibility = '--private' if private else '--public'
		arguments  = ['repo', 'create', new_repo, visibility]

		if from_repo is None:
			cls._gh(arguments)
		else:
			from_repo = cls._validate_repository(from_repo)

			with tempfile.TemporaryDirectory(prefix='almasi_git_') as directory:
				cls.clone(f'https://{cls._HOST}/{from_repo}.git', directory)
				cls._gh([*arguments, '--source', directory, '--remote', 'destination', '--push'])

		return f'https://{cls._HOST}/{new_repo}.git'
