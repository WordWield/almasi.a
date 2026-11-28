# ==============================================================================
# REFLECTION
# ==============================================================================
# PURPOSE:
# Discover declared methods and describe their callable contracts.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Method lookup, binding, enumeration and signature reflection.
# Delegates: Module metadata inspection to ReflectionMeta.
# ==============================================================================

import inspect
import typing

from .reflection_meta import ReflectionMeta


class Reflection(metaclass=ReflectionMeta):

	# ======================================================================
	# FRAMEWORK METHODS
	# ======================================================================

	# Resolve public declarations without evaluating arbitrary descriptors.
	# ----------------------------------------------------------------------
	def __get_method__(self, name, **attributes):
		declaration = inspect.getattr_static(type(self), name, None)
		method      = None

		if isinstance(declaration, (classmethod, staticmethod)):
			function = declaration.__func__
		else:
			function = declaration

		if (
			not name.startswith('_')
			and inspect.isfunction(function)
			and all(getattr(function, key, None) == value for key, value in attributes.items())
		):
			method = declaration.__get__(self, type(self))

		return method

	# Enumerate exactly the same public declarations as individual lookup.
	# ----------------------------------------------------------------------
	def __list_methods__(self, **attributes):
		for name in dir(type(self)):
			method = self.__get_method__(name, **attributes)

			if method is not None:
				yield method

	# Describe the class-declared method using its defining namespace.
	# ----------------------------------------------------------------------
	@classmethod
	def __get_method_signature__(cls, name):
		owner = next((base for base in cls.__mro__ if name in vars(base)), None)

		if owner is not None:
			declaration = vars(owner)[name]
			method      = declaration.__func__ if isinstance(declaration, (classmethod, staticmethod)) else declaration

			if inspect.isfunction(method):
				result = getattr(method, '__signature__', None)

				if not isinstance(result, dict):
					signature  = inspect.signature(method)
					localns    = {**vars(owner), owner.__name__: owner}
					hints      = typing.get_type_hints(method, localns=localns, include_extras=True)
					parameters = tuple(signature.parameters.values())
					inputs     = {}

					if not isinstance(declaration, staticmethod):
						parameters = parameters[1:]

					for parameter in parameters:
						field      = {}
						annotation = hints.get(parameter.name, parameter.annotation)

						if annotation is not inspect.Parameter.empty:
							field['type'] = annotation
						if parameter.default is not inspect.Parameter.empty:
							field['default'] = parameter.default
						if parameter.kind is not inspect.Parameter.POSITIONAL_OR_KEYWORD:
							field['kind'] = parameter.kind.name.lower()

						inputs[parameter.name] = field

					output     = {}
					annotation = hints.get('return', signature.return_annotation)

					if annotation is not inspect.Signature.empty:
						output['type'] = annotation

					result = {'inputs': inputs, 'output': output}
			else:
				raise TypeError(f'Not a method: {cls.__name__}.{name}')
		else:
			raise AttributeError(f'Method not found: {cls.__name__}.{name}')

		return result
