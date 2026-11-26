# ==============================================================================
# FILESYSTEM RESOURCE
# ==============================================================================
# PURPOSE:
# Represent a filesystem carrier in its effective library namespace.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Carrier identity in its supplying and effective namespaces.
# Delegates: Reading to concrete carriers and observation to Filesystem.
# ==============================================================================

import os
from importlib import import_module

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
		self._namespace_lib  = lib

	# Describe the carrier without realizing its content.
	# --------------------------------------------------------------------------
	def __repr__(self):
		return f'<{type(self).__name__} `{self.get_route()}` path=`{self.get_path()}`>'

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Import the published Almasi instance, not its entry module during startup.
	# ----------------------------------------------------------------------
	@property
	def _observe(self):
		return import_module('almasi.a').services.Filesystem.observe

	# ==========================================================================
	# PUBLIC METHODS
	# ==========================================================================

	# Return the canonical physical path.
	# --------------------------------------------------------------------------
	def get_path(self):
		return self.__path__

	# Keep existing notification coordinates unless a resource selects a base.
	# --------------------------------------------------------------------------
	def get_change_base(self):
		return None

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
