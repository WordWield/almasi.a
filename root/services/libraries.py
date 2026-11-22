# ==============================================================================
# LIBRARIES
# ==============================================================================
# PURPOSE:
# Acquire and prepare Almasi libraries before publishing their Python identities.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Git source acquisition, dependency preparation and loading readiness.
# Delegates: Python module publication to Imports and dependencies to pip.
# ==============================================================================

import os
import subprocess
import sys

import almasi


class Libraries(almasi.Singleton):

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Show native Almasi progress while executing a subprocess.
	# ----------------------------------------------------------------------
	def _run(
		self,
		name,
		operation,
		command,
		cwd     = None,
		timeout = None
	):
		label = f'almasi.{name}: {operation}'

		try:
			with almasi.Spinner(text=label, failure_label=f'❌ {label}'):
				subprocess.run(
					command,
					cwd            = cwd,
					capture_output = True,
					text           = True,
					timeout        = timeout,
					check          = True
				)
		except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
			details = getattr(error, 'stderr', None) or str(error)
			raise RuntimeError(f'{label} failed: {str(details).strip()}') from error

	# Keep the local checkout if Git cannot fetch or fast-forward.
	# ----------------------------------------------------------------------
	def _pull(self, name):
		try:
			self._run(
				name,
				'Checking for updates',
				['git', '-C', self.get_path(name), 'pull', '--ff-only', '--quiet'],
				timeout = 15
			)
		except RuntimeError as error:
			print(f'⚠️ almasi.{name}: using local version ({error.__cause__})')

	# Install requirements using the library's working directory.
	# ----------------------------------------------------------------------
	def _install_requirements(self, name):
		requirements = os.path.join(self.get_path(name), 'requirements.txt')

		if os.path.isfile(requirements):
			self._run(
				name,
				'Installing dependencies',
				[sys.executable, '-m', 'pip', 'install', '-r', requirements],
				cwd = self.get_path(name)
			)

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Resolve a shared source directory, with an optional environment override.
	# ----------------------------------------------------------------------
	def get_path(self, name):
		if not almasi._is_valid_library_name(name):
			raise ValueError(f'Invalid library name: {name!r}')

		directory = os.environ.get('ALMASI_PATH') or os.path.join(
			os.path.expanduser('~'), '.cache', 'almasi', 'libraries'
		)
		result = os.path.join(os.path.abspath(directory), 'almasi.' + name)
		return result

	# Resolve the trusted organization source; Git handles authentication.
	# ----------------------------------------------------------------------
	def get_url(self, name):
		base   = os.environ.get('ALMASI_GIT_BASE', 'https://github.com/WordWield').rstrip('/')
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
			os.makedirs(os.path.dirname(destination), exist_ok=True)
			self._run(
				name,
				'Cloning library',
				['git', 'clone', '--quiet', '--', self.get_url(name), destination]
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
				if os.path.exists(os.path.join(path, '.git')):
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
