# ==============================================================================
# LIBRARIES
# ==============================================================================
# PURPOSE:
# Acquire Almasi libraries and resolve their Python identities.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Library source availability and canonical import identity.
# Delegates: Git operations to Git and namespace publication to a.extend().
# ==============================================================================

import os
import subprocess
import sys

import a


class Libraries(a.Singleton):

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Configure the Git remote and prepare the shared checkout directory.
	# ----------------------------------------------------------------------
	def initialize(
		self,
		path,
		owner  = 'apodgorny',
		prefix = 'almasi.',
		ssh    = 'git@github.com'
	):
		self.path   = path
		self.owner  = owner
		self.prefix = prefix
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

	# Derive the Git remote address directly from the library name.
	# ----------------------------------------------------------------------
	def get_url(self, name):
		return f'{self.ssh}:{self.owner}/{self.prefix}{name}.git'

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
			path = self.clone(name)
			a.Imports.load_module(
				a,
				os.path.join(path, name + '.py'),
				module_name = qualified
			)
			library = sys.modules.get(qualified)

		if isinstance(library, a.A):
			result = library
		else:
			sys.modules.pop(qualified, None)
			raise ImportError(f'Not an Almasi library: {qualified}')

		return result
