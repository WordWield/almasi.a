# ==============================================================================
# STRICT
# ==============================================================================
# PURPOSE:
# Enforce declared types on ordinary calls to public methods of subclasses.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Declaration validation and automatic checked execution.
# Delegates: Reflection to Module and value matching to Annotation.
# ==============================================================================

import inspect
from functools import wraps

from almasi import a


class Strict(a.Module):

	# ======================================================================
	# FRAMEWORK METHODS
	# ======================================================================

	# Check new public declarations before making the class available.
	# ----------------------------------------------------------------------
	def __init_subclass__(cls, **kwargs):
		super().__init_subclass__(**kwargs)

		localns = {**vars(cls), cls.__name__: cls}

		for name, declaration in tuple(vars(cls).items()):
			if not name.startswith('_'):
				is_descriptor = isinstance(declaration, (classmethod, staticmethod))
				method        = declaration.__func__ if is_descriptor else declaration

				if inspect.isfunction(method):
					signature = cls.__get_method_signature__(
						method,
						localns    = localns,
						skip_owner = not isinstance(declaration, staticmethod)
					)

					is_typed = (
						all('type' in parameter for parameter in signature['inputs'].values())
						and 'type' in signature['output']
					)

					if is_typed:
						wrapped = cls._decorate_method(method, signature)
						setattr(cls, name, type(declaration)(wrapped) if is_descriptor else wrapped)
					else:
						raise TypeError(f'Incomplete annotations: {cls.__name__}.{name}')

	# Validate bound arguments, including defaults and variadic values.
	# ----------------------------------------------------------------------
	@classmethod
	def __validate_input__(cls, signature, arguments):
		for name, parameter in signature['inputs'].items():
			value = arguments[name]
			kind  = parameter.get('kind')

			if kind == 'var_positional':
				values = value
			elif kind == 'var_keyword':
				values = value.values()
			else:
				values = (value,)

			for item in values:
				cls._check_type(item, parameter['type'])

	# Validate the completed result without coercion or resource consumption.
	# ----------------------------------------------------------------------
	@classmethod
	def __validate_output__(cls, signature, output):
		cls._check_type(output, signature['output']['type'])

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Preserve native binding, coroutine identity and declaration metadata.
	# ----------------------------------------------------------------------
	@classmethod
	def _decorate_method(cls, method, signature):
		bind = inspect.signature(method).bind

		if inspect.iscoroutinefunction(method):
			@wraps(method)
			async def wrapped(*args, **kwargs):
				bound = bind(*args, **kwargs)
				bound.apply_defaults()
				cls.__validate_input__(signature, bound.arguments)

				output = await method(*args, **kwargs)
				cls.__validate_output__(signature, output)

				return output
		else:
			@wraps(method)
			def wrapped(*args, **kwargs):
				bound = bind(*args, **kwargs)
				bound.apply_defaults()
				cls.__validate_input__(signature, bound.arguments)

				output = method(*args, **kwargs)
				cls.__validate_output__(signature, output)

				return output

		wrapped.__signature__ = signature

		return wrapped

	# Return a matching value unchanged or reject its actual type.
	# ----------------------------------------------------------------------
	@staticmethod
	def _check_type(value, annotation):
		if a.Annotation(annotation).matches(value):
			result = value
		else:
			raise TypeError(f'Expected {annotation!r}, got {type(value)!r}')

		return result
