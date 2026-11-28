# ==============================================================================
# REFLECTION META
# ==============================================================================
# PURPOSE:
# Reflect the source module and its declared metadata from a class namespace.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Read-only inspection of module identity and source metadata.
# Delegates: Publishing class metadata to the consuming metaclass.
# ==============================================================================

import sys


class ReflectionMeta(type):

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Get module object
	# ----------------------------------------------------------------------
	@classmethod
	def module(mcls, namespace):
		return sys.modules.get(namespace.get('__module__'))

	# Get current library
	# ----------------------------------------------------------------------
	@classmethod
	def module_lib(mcls, namespace):
		return getattr(mcls.module(namespace), '__lib__', None)

	# Get carrier class name from route
	# ----------------------------------------------------------------------
	@classmethod
	def module_class_name(mcls, namespace):
		class_name = None
		route      = mcls.module_route(namespace)

		if route is not None:
			class_name = route.split('.')[-1]

		return class_name

	# Get module route from library resolver
	# ----------------------------------------------------------------------
	@classmethod
	def module_route(mcls, namespace):
		return getattr(mcls.module(namespace), '__route__', None)

	# Get module mtime from loader
	# ----------------------------------------------------------------------
	@classmethod
	def module_mtime(mcls, namespace):
		return getattr(mcls.module(namespace), '__mtime__', None)

	# Does class come from source file?
	# ----------------------------------------------------------------------
	@classmethod
	def has_own_module(mcls, namespace):
		class_name = mcls.module_class_name(namespace)
		short_name = namespace.get('__qualname__', '').split('.')[-1]

		return class_name is not None and short_name == class_name
