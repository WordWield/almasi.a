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

	# Check and decorate new public declarations once, before use.
	# ----------------------------------------------------------------------
	def __init_subclass__(cls, **kwargs):
		super().__init_subclass__(**kwargs)

		localns = {**vars(cls), cls.__name__: cls}

		for name, declaration in tuple(vars(cls).items()):
			if not name.startswith('_'):
				if isinstance(declaration, (classmethod, staticmethod)):
					method = declaration.__func__
				else:
					method = declaration

				if inspect.isfunction(method):
					signature = cls.__get_method_signature__(method, localns=localns)
					inputs    = tuple(signature.parameters.values())
					has_owner = not isinstance(declaration, staticmethod)

					if has_owner:
						inputs = inputs[1:]

					for parameter in inputs:
						if parameter.annotation is inspect.Parameter.empty:
							raise TypeError(f'Missing annotation: {cls.__name__}.{name}.{parameter.name}')

					if signature.return_annotation is inspect.Signature.empty:
						raise TypeError(f'Missing return annotation: {cls.__name__}.{name}')

					wrapped = cls._decorate_method(method, signature)

					if isinstance(declaration, classmethod):
						wrapped = classmethod(wrapped)
					elif isinstance(declaration, staticmethod):
						wrapped = staticmethod(wrapped)

					setattr(cls, name, wrapped)

	# Validate all actual input values using the stored native signature.
	# ----------------------------------------------------------------------
	@classmethod
	def __validate_input__(cls, signature, args, kwargs):
		bound = signature.bind(*args, **kwargs)
		bound.apply_defaults()

		for name, value in bound.arguments.items():
			parameter  = signature.parameters[name]
			annotation = parameter.annotation

			if annotation is not inspect.Parameter.empty:
				if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
					for item in value:
						cls._check_type(item, annotation)
				elif parameter.kind is inspect.Parameter.VAR_KEYWORD:
					for item in value.values():
						cls._check_type(item, annotation)
				else:
					cls._check_type(value, annotation)

	# Validate the completed result without coercion or consumption.
	# ----------------------------------------------------------------------
	@classmethod
	def __validate_output__(cls, signature, output):
		cls._check_type(output, signature.return_annotation)

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Keep native method binding, coroutine identity and decorator metadata.
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

	# Check a value without changing its type or state.
	# ----------------------------------------------------------------------
	@staticmethod
	def _check_type(value, annotation):
		if not a.Annotation(annotation).matches(value):
			raise TypeError(f'Expected {annotation!r}, got {type(value)!r}')
