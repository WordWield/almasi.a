# ==============================================================================
# MODULE META
# ==============================================================================
# PURPOSE:
# Associate Almasi source metadata with its carrier classes.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Library, route, modification time and carrier identity conventions.
# Delegates: Python module lookup to ReflectionMeta.
# ==============================================================================

from .reflection_meta import ReflectionMeta


class ModuleMeta(ReflectionMeta):

	# ======================================================================
	# FRAMEWORK METHODS
	# ======================================================================

	# Class creation
	# ----------------------------------------------------------------------
	def __new__(mcls, name, bases, namespace, **kwargs):
		namespace['__has_own_module__'] = mcls.has_own_module(namespace)
		if mcls.module_lib(namespace) is not None:
			namespace['__lib__'] = mcls.module_lib(namespace)

		if namespace['__has_own_module__']:
			namespace['__route__'] = mcls.module_route(namespace)
			namespace['__mtime__'] = mcls.module_mtime(namespace)

		return super().__new__(mcls, name, bases, namespace)

	# String representation
	# ----------------------------------------------------------------------
	def __repr__(cls):
		text  = cls.__name__
		route = getattr(cls, '__route__', None)

		if isinstance(route, str):
			text = route

		return f'<class \'{text}\'>'

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

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
