# ==============================================================================
# LIBRARIES
# ==============================================================================
# Acquire Almasi source libraries and publish their canonical Python identities.
# ==============================================================================

import os
import subprocess
import sys

import a


class Libraries(a.Singleton):

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Resolve a shared source directory, with an optional environment override.
	# ----------------------------------------------------------------------
	def get_path(self, name):
		if not a._is_valid_library_name(name):
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
			subprocess.run(
				['git', 'clone', '--quiet', '--', self.get_url(name), destination],
				check = True
			)

		return destination

	# Reuse the published library or execute its source under its qualified name.
	# ----------------------------------------------------------------------
	def imp(self, name):
		qualified = f'almasi.{name}'
		library   = sys.modules.get(qualified)

		if library is None:
			path  = self.clone(name)
			entry = os.path.join(path, name + '.py')

			if not os.path.isfile(entry):
				entry = os.path.join(path, 'almasi', name + '.py')

			a.Imports.load_module(
				a,
				entry,
				module_name = qualified
			)
			library = sys.modules.get(qualified)

		if not isinstance(library, a.A):
			raise ImportError(f'Not an Almasi library: {qualified}')

		return library
