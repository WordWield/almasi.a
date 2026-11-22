# ==============================================================================
# LIBRARIES SERVICE
# ==============================================================================
# Discover Almasi repositories and acquire libraries without owning imports.
# ==============================================================================
 
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request

from .singleton import Singleton


class Libraries(Singleton):

	_lock = threading.RLock()

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Use the selected repository owner without embedding credentials.
	# ----------------------------------------------------------------------
	def _owner(self):
		owner = os.environ.get('ALMASI_LIBRARY_OWNER', 'apodgorny')

		if re.fullmatch(r'[A-Za-z0-9-]+', owner) is None:
			raise ValueError('Invalid ALMASI_LIBRARY_OWNER')

		return owner

	# Keep acquired libraries in one user-owned directory.
	# ----------------------------------------------------------------------
	def _directory(self):
		directory = os.environ.get('ALMASI_LIBRARY_DIR', '~/.almasi/libraries')
		return os.path.realpath(os.path.expanduser(directory))

	# Reuse Almasi's canonical library name validation.
	# ----------------------------------------------------------------------
	def _validate(self, name):
		import a

		if not a._is_valid_library_name(name):
			raise ValueError(f'Invalid Almasi library name: {name!r}')

		return name

	# A complete checkout has its entry module and Almasi source root.
	# ----------------------------------------------------------------------
	def _is_local(self, name):
		directory = os.path.join(self._directory(), name)
		return (
			os.path.isfile(os.path.join(directory, name + '.py'))
			and os.path.isdir(os.path.join(directory, 'root'))
		)

	# Read one public GitHub API response without creating an auth session.
	# ----------------------------------------------------------------------
	def _github(self, url):
		request = urllib.request.Request(url, headers={
			'Accept'     : 'application/vnd.github+json',
			'User-Agent' : 'Almasi-Libraries'
		})

		with urllib.request.urlopen(request, timeout=15) as response:
			data = json.load(response)

		return data

	# Enumerate public libraries from a user or organization.
	# ----------------------------------------------------------------------
	def _public_repositories(self, owner):
		account = self._github(f'https://api.github.com/users/{owner}')
		scope   = 'orgs' if account.get('type') == 'Organization' else 'users'
		result  = {}
		page    = 1

		while True:
			url   = f'https://api.github.com/{scope}/{owner}/repos?per_page=100&page={page}'
			repos = self._github(url)

			if not isinstance(repos, list):
				raise RuntimeError('Invalid GitHub repository listing')

			for repo in repos:
				name = repo.get('name', '')

				if name.startswith('almasi.'):
					library = name.removeprefix('almasi.')

					if self._valid_repository_name(library):
						result[library] = repo['clone_url']

			if len(repos) < 100:
				break

			page += 1

		return result

	# Keep repository discovery names consistent with Almasi source names.
	# ----------------------------------------------------------------------
	def _valid_repository_name(self, name):
		import a
		return a._is_valid_library_name(name)

	# Use an existing GitHub CLI login for private listing when available.
	# The CLI is optional; SSH credentials alone cannot list private repos.
	# ----------------------------------------------------------------------
	def _remote_repositories(self):
		owner  = self._owner()
		result = {}

		if shutil.which('gh') is not None:
			command = [
				'gh', 'repo', 'list', owner, '--limit', '1000',
				'--json', 'name,isPrivate,sshUrl,url'
			]
			proc = subprocess.run(command, capture_output=True, text=True, timeout=20)

			if proc.returncode == 0:
				for repo in json.loads(proc.stdout):
					name = repo.get('name', '')

					if name.startswith('almasi.'):
						library = name.removeprefix('almasi.')

						if self._valid_repository_name(library):
							result[library] = (
								repo['sshUrl'] if repo['isPrivate']
								else repo['url'] + '.git'
							)

		if not result:
			result = self._public_repositories(owner)

		return result

	# Load a checked-out entry point under its qualified Almasi identity.
	# Existing a.extend() owns publication of the canonical library.
	# ----------------------------------------------------------------------
	def _import_local(self, name):
		import a

		qualified = 'almasi.' + name
		entry     = os.path.join(self._directory(), name, name + '.py')
		spec      = importlib.util.spec_from_file_location(qualified, entry)

		if spec is None or spec.loader is None:
			raise ImportError(f'Cannot load Almasi library: {qualified}')

		module = importlib.util.module_from_spec(spec)
		sys.modules[qualified] = module

		try:
			spec.loader.exec_module(module)
			library = sys.modules.get(qualified)

			if not isinstance(library, a.A):
				raise ImportError(f'Library did not publish {qualified} through a.extend()')
		except BaseException:
			sys.modules.pop(qualified, None)
			raise

		return library

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# List known local and remotely discoverable Almasi libraries.
	# Remote private repositories require an existing GitHub CLI login.
	# ----------------------------------------------------------------------
	def list(self):
		import a

		directory = self._directory()
		local     = set()

		if os.path.isdir(directory):
			local = {
				name for name in os.listdir(directory)
				if self._valid_repository_name(name) and self._is_local(name)
			}

		loaded = {
			name.removeprefix('almasi.') for name, module in sys.modules.items()
			if name.startswith('almasi.') and isinstance(module, a.A)
		}

		return sorted(local | loaded | self._remote_repositories().keys())

	# Acquire an absent library, keeping incomplete clones out of the cache.
	# A private repository can be fetched by name with local SSH credentials.
	# ----------------------------------------------------------------------
	def clone(self, name):
		name        = self._validate(name)
		directory   = self._directory()
		destination = os.path.join(directory, name)

		with self._lock:
			if not self._is_local(name):
				if os.path.lexists(destination):
					raise FileExistsError(f'Incomplete local library: {destination}')

				repositories = self._remote_repositories()
				source       = repositories.get(
					name, f'git@github.com:{self._owner()}/almasi.{name}.git'
				)

				os.makedirs(directory, exist_ok=True)
				stage    = tempfile.mkdtemp(prefix='.almasi-', dir=directory)
				checkout = os.path.join(stage, 'checkout')

				try:
					subprocess.run(['git', 'clone', '--quiet', '--', source, checkout], check=True)

					if not (
						os.path.isfile(os.path.join(checkout, name + '.py'))
						and os.path.isdir(os.path.join(checkout, 'root'))
					):
						raise ImportError(f'Not an Almasi library repository: {source}')

					os.rename(checkout, destination)
				finally:
					shutil.rmtree(stage)

		return destination

	# Resolve once, acquire when absent, and reuse Python's canonical module.
	# ----------------------------------------------------------------------
	def imp(self, name):
		import a

		name      = self._validate(name)
		qualified = 'almasi.' + name

		with self._lock:
			library = sys.modules.get(qualified)

			if library is None:
				if not self._is_local(name):
					self.clone(name)

				library = self._import_local(name)

			if not isinstance(library, a.A):
				raise ImportError(f'Not an Almasi library: {qualified}')

		return library
