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
	# PRIVATE METHODS
	# ======================================================================

	# Reject names that cannot identify a single Almasi repository.
	# ----------------------------------------------------------------------
	def _validate_name(self, name):
		if not a._is_valid_library_name(name):
			raise ValueError(f'Invalid library name: {name!r}')

	# Find an entry point without exposing a top-level module that might
	# shadow an unrelated Python package, such as the official MCP SDK.
	# ----------------------------------------------------------------------
	def _get_entry_path(self, path, name):
		nested = os.path.join(path, 'almasi', name + '.py')
		direct = os.path.join(path, name + '.py')
		result = nested if os.path.isfile(nested) else direct
		return result

	# A checkout is usable only when both its entry point and root exist.
	# ----------------------------------------------------------------------
	def _is_checkout(self, path, name):
		result = (
			os.path.isfile(self._get_entry_path(path, name))
			and os.path.isdir(os.path.join(path, 'root'))
		)
		return result

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Resolve a shared source directory, with an optional environment override.
	# ----------------------------------------------------------------------
	def get_path(self, name):
		self._validate_name(name)
		directory = os.environ.get('ALMASI_PATH') or os.path.join(
			os.path.expanduser('~'), '.cache', 'almasi', 'libraries'
		)
		result = os.path.join(os.path.abspath(directory), 'almasi.' + name)
		return result

	# Resolve the trusted organization source; Git handles authentication.
	# ----------------------------------------------------------------------
	def get_url(self, name):
		self._validate_name(name)
		base   = os.environ.get('ALMASI_GIT_BASE', 'https://github.com/WordWield').rstrip('/')
		result = f'{base}/almasi.{name}.git'
		return result

	# Recognize a locally available library without contacting Git.
	# ----------------------------------------------------------------------
	def is_cloned(self, name):
		result = self._is_checkout(self.get_path(name), name)
		return result

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
		self._validate_name(name)
		qualified = f'almasi.{name}'
		library   = sys.modules.get(qualified)

		if library is None:
			path = self.clone(name)
			a.Imports.load_module(
				a,
				self._get_entry_path(path, name),
				module_name = qualified
			)
			library = sys.modules.get(qualified)

		if not isinstance(library, a.A):
			raise ImportError(f'Not an Almasi library: {qualified}')

		return library
