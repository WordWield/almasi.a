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
from functools import partial

import almasi


class Libraries(almasi.Singleton):

	_DEFAULT_GIT_BASE = 'https://github.com/WordWield'
	_DEFAULT_CACHE    = '~/.cache/almasi/libraries'
	_PULL_TIMEOUT     = 15

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Report acquisition progress without coupling Git to library policy.
	# ----------------------------------------------------------------------
	def _run(self, name, operation, action):
		label = f'almasi.{name}: {operation}'

		try:
			with almasi.Spinner(text=label, stream=sys.stderr, failure_label=f'❌ {label}'):
				action()
		except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
			details = getattr(error, 'stderr', None) or str(error)
			raise RuntimeError(f'{label} failed: {str(details).strip()}') from error

	# Keep the local checkout if Git cannot fetch or fast-forward.
	# ----------------------------------------------------------------------
	def _pull(self, name):
		try:
			if almasi.services.Git.is_repository(self.get_path(name)):
				self._run(
					name,
					'Checking for updates',
					partial(almasi.services.Git.pull, self.get_path(name), timeout=self._PULL_TIMEOUT)
				)
		except (RuntimeError, OSError) as error:
			print(f'⚠️ almasi.{name}: using local version ({error.__cause__ or error})', file=sys.stderr)

	# Install requirements using the library's working directory.
	# ----------------------------------------------------------------------
	def _install_requirements(self, name):
		requirements = os.path.join(self.get_path(name), 'requirements.txt')

		if os.path.isfile(requirements):
			self._run(
				name,
				'Installing dependencies',
				partial(
					subprocess.run,
					[sys.executable, '-m', 'pip', 'install', '-r', requirements],
					cwd            = self.get_path(name),
					capture_output = True,
					text           = True,
					check          = True
				)
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
			self._run(
				name,
				'Cloning library',
				partial(almasi.services.Git.clone, self.get_url(name), destination)
			)

		return destination

	# Reuse a loaded library; otherwise prepare source and its dependencies.
	# ----------------------------------------------------------------------
	def imp(self, name):
		qualified = f'almasi.{name}'
		library   = sys.modules.get(qualified)

		if library is None:
			path = self.get_path(name)

			if self.is_cloned(name):
				self._pull(name)
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
