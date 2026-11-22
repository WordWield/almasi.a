# ==============================================================================
# LIBRARIES
# ==============================================================================
# PURPOSE:
# Discover and acquire Almasi libraries, then resolve their Python identity.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Library source availability and local acquisition.
# Delegates: Python source execution to Imports and Git operations to Git.
# Does not own authentication, projects, or application initialization.
# ==============================================================================

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

import a


class Libraries(a.Singleton):

	DEFAULT_OWNER     = 'apodgorny'
	DEFAULT_DIRECTORY = '~/.almasi/libraries'
	REPOSITORY_PREFIX = 'almasi.'
	GITHUB_API        = 'https://api.github.com'
	GITHUB_SSH        = 'git@github.com'

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Resolve the repository owner without introducing an auth dependency.
	# ----------------------------------------------------------------------
	def _owner(self):
		owner = os.environ.get('ALMASI_LIBRARY_OWNER', self.DEFAULT_OWNER)

		if re.fullmatch(r'[A-Za-z0-9-]+', owner):
			result = owner
		else:
			raise ValueError('Invalid ALMASI_LIBRARY_OWNER')

		return result

	# Locate acquired sources independently of any active project.
	# ----------------------------------------------------------------------
	def _directory(self):
		directory = os.environ.get('ALMASI_LIBRARY_DIR', self.DEFAULT_DIRECTORY)
		return os.path.realpath(os.path.expanduser(directory))

	# Reject names that cannot be canonical Almasi library identities.
	# ----------------------------------------------------------------------
	def _validate(self, name):
		if a._is_valid_library_name(name):
			result = name
		else:
			raise ValueError(f'Invalid Almasi library name: {name!r}')

		return result

	# Recognize only complete library checkouts.
	# ----------------------------------------------------------------------
	def _is_local(self, name):
		directory = os.path.join(self._directory(), name)
		return (
			os.path.isfile(os.path.join(directory, name + '.py'))
			and os.path.isdir(os.path.join(directory, 'root'))
		)

	# Fetch public GitHub metadata without requiring any credentials.
	# ----------------------------------------------------------------------
	def _github(self, url):
		request = urllib.request.Request(url, headers={
			'Accept'     : 'application/vnd.github+json',
			'User-Agent' : 'Almasi-Libraries'
		})

		with urllib.request.urlopen(request, timeout=15) as response:
			result = json.load(response)

		return result

	# Discover all public library repositories of a user or organization.
	# ----------------------------------------------------------------------
	def _public_repositories(self, owner):
		account = self._github(f'{self.GITHUB_API}/users/{owner}')
		scope   = 'orgs' if account.get('type') == 'Organization' else 'users'
		result  = {}
		page    = 1

		while True:
			url   = f'{self.GITHUB_API}/{scope}/{owner}/repos?per_page=100&page={page}'
			repos = self._github(url)

			if isinstance(repos, list):
				for repo in repos:
					repository_name = repo.get('name', '')

					if repository_name.startswith(self.REPOSITORY_PREFIX):
						name = repository_name.removeprefix(self.REPOSITORY_PREFIX)

						if a._is_valid_library_name(name):
							result[name] = repo['clone_url']

				if len(repos) < 100:
					break

				page += 1
			else:
				raise RuntimeError('Invalid GitHub repository listing')

		return result

	# Discover private repositories when the GitHub CLI is already signed in.
	# ----------------------------------------------------------------------
	def _cli_repositories(self, owner):
		command = [
			'gh', 'repo', 'list', owner, '--limit', '1000',
			'--json', 'name,isPrivate,sshUrl,url'
		]
		process = subprocess.run(
			command,
			capture_output = True,
			text           = True,
			check          = False,
			timeout        = 20
		)

		if process.returncode == 0:
			result = {}

			for repo in json.loads(process.stdout):
				repository_name = repo.get('name', '')

				if repository_name.startswith(self.REPOSITORY_PREFIX):
					name = repository_name.removeprefix(self.REPOSITORY_PREFIX)

					if a._is_valid_library_name(name):
						result[name] = (
							repo['sshUrl'] if repo['isPrivate']
							else repo['url'] + '.git'
						)
		else:
			result = None

		return result

	# Prefer existing CLI access, otherwise use anonymous public discovery.
	# ----------------------------------------------------------------------
	def _remote_repositories(self):
		owner  = self._owner()
		result = self._cli_repositories(owner) if shutil.which('gh') else None

		if result is None:
			result = self._public_repositories(owner)

		return result

	# Import with the existing source loader and canonical a.extend identity.
	# ----------------------------------------------------------------------
	def _import_local(self, name):
		qualified = 'almasi.' + name
		entry     = os.path.join(self._directory(), name, name + '.py')

		a.Imports.load_module(a, entry, qualified_name=qualified)
		library = sys.modules.get(qualified)

		if isinstance(library, a.A):
			result = library
		else:
			sys.modules.pop(qualified, None)
			raise ImportError(f'Source did not publish {qualified} via a.extend()')

		return result

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# List locally acquired, imported and discoverable remote libraries.
	# ----------------------------------------------------------------------
	def list(self):
		directory = self._directory()
		local     = set()

		if os.path.isdir(directory):
			local = {
				name for name in os.listdir(directory)
				if a._is_valid_library_name(name) and self._is_local(name)
			}

		loaded = {
			name.removeprefix('almasi.')
			for name, module in sys.modules.copy().items()
			if name.startswith('almasi.') and isinstance(module, a.A)
		}

		return sorted(local | loaded | self._remote_repositories().keys())

	# Clone to a temporary Git checkout and publish only a complete source.
	# ----------------------------------------------------------------------
	def clone(self, name):
		name        = self._validate(name)
		directory   = self._directory()
		destination = os.path.join(directory, name)

		if not self._is_local(name):
			if not os.path.lexists(destination):
				repositories = self._remote_repositories()
				source       = repositories.get(
					name,
					f'{self.GITHUB_SSH}:{self._owner()}/{self.REPOSITORY_PREFIX}{name}.git'
				)

				os.makedirs(directory, exist_ok=True)
				stage    = tempfile.mkdtemp(prefix='.almasi-', dir=directory)
				checkout = os.path.join(stage, 'checkout')

				try:
					process = subprocess.run(
						['git', 'clone', '--quiet', '--', source, checkout],
						capture_output = True,
						text           = True,
						check          = False
					)

					if process.returncode == 0:
						is_valid = (
							os.path.isfile(os.path.join(checkout, name + '.py'))
							and os.path.isdir(os.path.join(checkout, 'root'))
						)

						if is_valid:
							# Another successful clone may have published first.
							# ------------------------------------------------------
							try:
								os.rename(checkout, destination)
							except OSError:
								if not self._is_local(name):
									raise
						else:
							raise ImportError(f'Not an Almasi library repository: {source}')
					else:
						raise ImportError(f'Cannot clone {source}: {process.stderr.strip()}')
				finally:
					shutil.rmtree(stage)
			else:
				raise FileExistsError(f'Incomplete local library: {destination}')

		return destination

	# Reuse an imported library or acquire and load its missing source.
	# ----------------------------------------------------------------------
	def imp(self, name):
		name      = self._validate(name)
		qualified = 'almasi.' + name
		library   = sys.modules.get(qualified)

		if library is None:
			if not self._is_local(name):
				self.clone(name)

			library = self._import_local(name)

		if isinstance(library, a.A):
			result = library
		else:
			raise ImportError(f'Not an Almasi library: {qualified}')

		return result
