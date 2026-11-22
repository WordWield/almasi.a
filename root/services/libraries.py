# ==============================================================================
# LIBRARIES
# ==============================================================================
# PURPOSE:
# Acquire Almasi libraries and resolve their Python identities.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Library discovery and local source availability.
# Delegates: Git operations to Git and namespace publication to a.extend().
# ==============================================================================

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import urllib.request

import a


class Libraries(a.Singleton):

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# List all repositories visible through GitHub or the authenticated CLI.
	# ----------------------------------------------------------------------
	def _list_all_repos(self):
		owner   = self.owner
		command = ['gh', 'repo', 'list', owner, '--limit', '1000',
				   '--json', 'name,isPrivate,sshUrl,url']
		cli     = subprocess.run(command, capture_output=True, text=True, timeout=20) if shutil.which('gh') else None

		if cli is not None and cli.returncode == 0:
			repos = {
				repo['name']: repo['sshUrl'] if repo['isPrivate']
				else repo['url'] + '.git'
				for repo in json.loads(cli.stdout)
			}
		else:
			with urllib.request.urlopen(f'{self.api}/users/{owner}', timeout=15) as response:
				scope = 'orgs' if json.load(response)['type'] == 'Organization' else 'users'

			repos = {}
			page  = 1

			while True:
				url = f'{self.api}/{scope}/{owner}/repos?per_page=100&page={page}'
				with urllib.request.urlopen(url, timeout=15) as response:
					entries = json.load(response)

				repos.update({repo['name']: repo['clone_url'] for repo in entries})
				if len(entries) < 100:
					break
				page += 1

		return repos

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Configure the GitHub source and prepare the shared checkout directory.
	# ----------------------------------------------------------------------
	def initialize(
		self,
		path,
		owner  = 'apodgorny',
		prefix = 'almasi.',
		api    = 'https://api.github.com',
		ssh    = 'git@github.com'
	):
		self.path   = path
		self.owner  = owner
		self.prefix = prefix
		self.api    = api
		self.ssh    = ssh

		os.makedirs(self.path, exist_ok=True)

	# Derive a library's checkout from its name and shared library path.
	# ----------------------------------------------------------------------
	def get_path(self, name):
		return os.path.join(self.path, self.prefix + name)

	# Check whether a complete checkout already exists.
	# ----------------------------------------------------------------------
	def is_cloned(self, name):
		path = self.get_path(name)
		return (os.path.isfile(os.path.join(path, name + '.py'))
				and os.path.isdir(os.path.join(path, 'root')))

	# Resolve the known repository URL, using SSH for undiscoverable names.
	# ----------------------------------------------------------------------
	def get_url(self, name):
		owner = self.owner
		return self._list_all_repos().get(
			self.prefix + name, f'{self.ssh}:{owner}/{self.prefix}{name}.git'
		)

	# Discover Almasi library names from the repository catalogue.
	# ----------------------------------------------------------------------
	def list(self):
		repos = self._list_all_repos()
		return sorted(
			name.removeprefix(self.prefix)
			for name in repos
			if name.startswith(self.prefix)
			and a._is_valid_library_name(name.removeprefix(self.prefix))
		)

	# Get source with Git; publish only a complete checkout.
	# ----------------------------------------------------------------------
	def clone(self, name):
		if a._is_valid_library_name(name):
			destination = self.get_path(name)

			if not self.is_cloned(name):
				source = self.get_url(name)
				subprocess.run(['git', 'clone', '--quiet', '--', source, destination], check=True)

		else:
			raise ValueError(f'Invalid library name: {name!r}')

		return destination

	# Publish the source under its canonical Almasi Python module name.
	# ----------------------------------------------------------------------
	def imp(self, name):
		qualified = f'almasi.{name}'
		library   = sys.modules.get(qualified)

		if library is None:
			path   = self.clone(name)
			spec   = importlib.util.spec_from_file_location(qualified, os.path.join(path, name + '.py'))
			module = importlib.util.module_from_spec(spec)
			sys.modules[qualified] = module

			try:
				spec.loader.exec_module(module)
			except Exception:
				sys.modules.pop(qualified, None)
				raise

			library = sys.modules.get(qualified)

		if isinstance(library, a.A):
			result = library
		else:
			sys.modules.pop(qualified, None)
			raise ImportError(f'Not an Almasi library: {qualified}')

		return result
