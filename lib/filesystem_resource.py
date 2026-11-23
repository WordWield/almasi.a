# ==============================================================================
# FILESYSTEM RESOURCE
# ==============================================================================
# Represent a filesystem carrier with its library namespace and watcher.
# ==============================================================================

import os

from .resource import Resource


class FilesystemResource(Resource):

	# ==========================================================================
	# FRAMEWORK METHODS
	# ==========================================================================

	# Keep source ownership distinct from the namespace through which it is seen.
	# --------------------------------------------------------------------------
	def __init__(self, lib, path, route):
		self.__lib__         = lib
		self.__path__        = os.path.realpath(path)
		self.__route__       = route
		self._namespace_lib = lib

	# Describe the carrier without realizing its content.
	# --------------------------------------------------------------------------
	def __repr__(self):
		return f'<{type(self).__name__} `{self.get_route()}` path=`{self.get_path()}`>'

	# ==========================================================================
	# PUBLIC METHODS
	# ==========================================================================

	# Return the canonical physical path.
	# --------------------------------------------------------------------------
	def get_path(self):
		return self.__path__

	# Return the logical route in the Almasi namespace.
	# --------------------------------------------------------------------------
	def get_route(self):
		return self.__route__

	# Return the library that supplied this filesystem carrier.
	# --------------------------------------------------------------------------
	def get_lib(self):
		return self.__lib__

	# Return the physical filename or directory name.
	# --------------------------------------------------------------------------
	def get_name(self):
		return os.path.basename(self.__path__)

	# Return the physical basename without its final extension.
	# --------------------------------------------------------------------------
	def get_stem(self):
		return os.path.splitext(self.get_name())[0]

	# Read through the existing format plugin or directory loader.
	# --------------------------------------------------------------------------
	def read(self):
		return self.load()

	# Observe the effective resource without owning a filesystem watcher.
	# --------------------------------------------------------------------------
	def subscribe(self, callback):
		return self._namespace_lib.services.Filesystem.subscribe({self}, callback)
