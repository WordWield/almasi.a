# ==============================================================================
# LIBRARIES
# ==============================================================================
# PURPOSE:
# Acquire and prepare Almasi libraries before publishing their Python identities.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Library source selection, cache policy and loading readiness.
# Delegates: Git operations to Git, publication to Imports, dependencies to pip.
# ==============================================================================

import os
import subprocess
import sys

import almasi


class Libraries(almasi.Singleton):

	_DEFAULT_GIT_BASE = 'https://github.com/WordWield'
	_DEFAULT_CACHE    = '~/.cache/almasi/libraries'
	_PULL_TIMEOUT     = 15

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Install requirements using the library's working directory.
	# ----------------------------------------------------------------------
	def _install_requirements(self, name):
		requirements = os.path.join(self.get_path(name), 'requirements.txt')

		if os.path.isfile(requirements):
			with almasi.Progress(f'almasi.{name}: Installing dependencies'):
				subprocess.run(
					[sys.executable, '-m', 'pip', 'install', '-r', requirements],
					cwd            = self.get_path(name),
					capture_output = True,
					text           = True,
					check          = True
				)

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Resolve a shared source directory, with an optional environment override.
	# ----------------------------------------------------------------------
	def get_path(self, name):
		if almasi._is_valid_library_name(name):
			directory = os.environ.get('ALMASI_PATH') or os.path.expanduser(self._DEFAULT_CACHE)
			result    = os.path.join(os.path.abspath(directory), 'almasi.' + name)
		else:
			raise ValueError(f'Invalid library name: {name!r}')

		return result

	# Resolve the trusted organization source; Git handles authentication.
	# ----------------------------------------------------------------------
	def get_url(self, name):
		base   = os.environ.get('ALMASI_GIT_BASE', self._DEFAULT_GIT_BASE).rstrip('/')
		result = f'{base}/almasi.{name}.git'
		return result

	# Recognize a locally available library without contacting Git.
	# ----------------------------------------------------------------------
	def is_cloned(self, name):
		return os.path.isdir(self.get_path(name))

	# Clone missing source into its local library directory.
	# ----------------------------------------------------------------------
	def clone(self, name):
		destination = self.get_path(name)

		if not self.is_cloned(name):
			with almasi.Progress(f'almasi.{name}: Cloning library'):
				almasi.services.Git.clone(self.get_url(name), destination)

		return destination

	# Reuse a loaded library; otherwise prepare source and its dependencies.
	# ----------------------------------------------------------------------
	def imp(self, name):
		qualified = f'almasi.{name}'
		library   = sys.modules.get(qualified)

		if library is None:
			path = self.get_path(name)

			if self.is_cloned(name):
				git = almasi.services.Git

				try:
					if git.is_repository(path):
						with almasi.Progress(f'almasi.{name}: Checking for updates'):
							git.pull(path, timeout=self._PULL_TIMEOUT)
				except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
					details = getattr(error, 'stderr', None) or str(error)
					print(f'⚠️ almasi.{name}: using local version ({str(details).strip()})', file=sys.stderr)
			else:
				path = self.clone(name)

			self._install_requirements(name)

			entry = os.path.join(path, name + '.py')

			if not os.path.isfile(entry):
				entry = os.path.join(path, 'almasi', name + '.py')

			almasi.Imports.load_module(
				almasi,
				entry,
				module_name = qualified
			)
			library = sys.modules.get(qualified)

		if isinstance(library, almasi.A):
			result = library
		else:
			raise ImportError(f'Not an Almasi library: {qualified}')

		return result
