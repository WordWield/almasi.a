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
					signature = cls.__get_method_signature__(method, localns=localns)
					inputs    = tuple(signature.parameters.values())[0 if isinstance(declaration, staticmethod) else 1:]

					is_typed = (
						all(parameter.annotation is not inspect.Parameter.empty for parameter in inputs)
						and signature.return_annotation is not inspect.Signature.empty
					)

					if is_typed:
						wrapped = cls._decorate_method(method, signature)
						setattr(cls, name, type(declaration)(wrapped) if is_descriptor else wrapped)
					else:
						raise TypeError(f'Incomplete annotations: {cls.__name__}.{name}')

	# Validate bound arguments, including defaults and variadic values.
	# ----------------------------------------------------------------------
	@classmethod
	def __validate_input__(cls, signature, args, kwargs):
		bound = signature.bind(*args, **kwargs)
		bound.apply_defaults()

		for name, value in bound.arguments.items():
			parameter = signature.parameters[name]

			if parameter.annotation is not inspect.Parameter.empty:
				if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
					values = value
				elif parameter.kind is inspect.Parameter.VAR_KEYWORD:
					values = value.values()
				else:
					values = (value,)

				for item in values:
					cls._check_type(item, parameter.annotation)

	# Validate the completed result without coercion or resource consumption.
	# ----------------------------------------------------------------------
	@classmethod
	def __validate_output__(cls, signature, output):
		cls._check_type(output, signature.return_annotation)

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Preserve native binding, coroutine identity and declaration metadata.
	# ----------------------------------------------------------------------
	@classmethod
	def _decorate_method(cls, method, signature):
		if inspect.iscoroutinefunction(method):
			@wraps(method)
			async def wrapped(*args, **kwargs):
				cls.__validate_input__(signature, args, kwargs)

				output = await method(*args, **kwargs)
				cls.__validate_output__(signature, output)

				return output
		else:
			@wraps(method)
			def wrapped(*args, **kwargs):
				cls.__validate_input__(signature, args, kwargs)

				output = method(*args, **kwargs)
				cls.__validate_output__(signature, output)

				return output

		wrapped.__signature__ = signature

		return wrapped

	# Return a matching value unchanged or reject its actual type.
	# ----------------------------------------------------------------------
	@staticmethod
	def _check_type(value, annotation):
		if not a.Annotation(annotation).matches(value):
			raise TypeError(f'Expected {annotation!r}, got {type(value)!r}')
		return value
