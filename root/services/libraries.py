# ==============================================================================
# LIBRARIES
# ==============================================================================
# PURPOSE:
# Acquire Almasi libraries and resolve their Python identities.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Library discovery and local source availability.
# Delegates: Git operations to Git and source execution to Imports.
# ==============================================================================

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

import a


class Libraries(a.Singleton):

	OWNER     = 'apodgorny'
	DIRECTORY = '~/.almasi/libraries'
	PREFIX    = 'almasi.'
	API       = 'https://api.github.com'
	SSH       = 'git@github.com'

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Check whether source is ready for Python import.
	# ----------------------------------------------------------------------
	def _is_local(self, name, path):
		return (os.path.isfile(os.path.join(path, name + '.py'))
				and os.path.isdir(os.path.join(path, 'root')))

	# Discover public libraries or those visible to an existing gh login.
	# ----------------------------------------------------------------------
	def _repositories(self):
		owner   = os.environ.get('ALMASI_LIBRARY_OWNER', self.OWNER)
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
			with urllib.request.urlopen(f'{self.API}/users/{owner}', timeout=15) as response:
				scope = 'orgs' if json.load(response)['type'] == 'Organization' else 'users'

			repos = {}
			page  = 1

			while True:
				url = f'{self.API}/{scope}/{owner}/repos?per_page=100&page={page}'
				with urllib.request.urlopen(url, timeout=15) as response:
					entries = json.load(response)

				repos.update({repo['name']: repo['clone_url'] for repo in entries})
				if len(entries) < 100:
					break
				page += 1

		return {
			name.removeprefix(self.PREFIX): url
			for name, url in repos.items()
			if name.startswith(self.PREFIX)
			and a._is_valid_library_name(name.removeprefix(self.PREFIX))
		}

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Discover currently published libraries on GitHub.
	# ----------------------------------------------------------------------
	def list(self):
		return sorted(self._repositories())

	# Get source with Git; publish only a complete checkout.
	# ----------------------------------------------------------------------
	def clone(self, name):
		if a._is_valid_library_name(name):
			directory   = os.path.realpath(os.path.expanduser(
				os.environ.get('ALMASI_LIBRARY_DIR', self.DIRECTORY)
			))
			destination = os.path.join(directory, name)

			if not self._is_local(name, destination):
				owner  = os.environ.get('ALMASI_LIBRARY_OWNER', self.OWNER)
				source = self._repositories().get(
					name, f'{self.SSH}:{owner}/{self.PREFIX}{name}.git'
				)

				os.makedirs(directory, exist_ok=True)
				with tempfile.TemporaryDirectory(dir=directory) as stage:
					checkout = os.path.join(stage, 'checkout')
					subprocess.run(['git', 'clone', '--quiet', '--', source, checkout], check=True)

					if self._is_local(name, checkout):
						try:
							os.rename(checkout, destination)
						except OSError:
							if not self._is_local(name, destination):
								raise
					else:
						raise ImportError(f'Invalid Almasi library: {source}')
		else:
			raise ValueError(f'Invalid library name: {name!r}')

		return destination

	# Reuse Python's published identity or delegate checked-out source.
	# ----------------------------------------------------------------------
	def imp(self, name):
		qualified = f'almasi.{name}'
		library   = sys.modules.get(qualified)

		if library is None:
			path = self.clone(name)
			a.Imports.load_module(a, os.path.join(path, name + '.py'), qualified_name=qualified)
			library = sys.modules.get(qualified)

		if not isinstance(library, a.A):
			sys.modules.pop(qualified, None)
			raise ImportError(f'Not an Almasi library: {qualified}')

		return library
