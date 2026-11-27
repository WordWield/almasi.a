# ==============================================================================
# STRICT
# ==============================================================================
# PURPOSE:
# Check explicitly invoked Python methods against their declared types.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Signature binding and runtime type checks.
# Delegates: Execution to the original callable; no implicit method wrapping.
# ==============================================================================

import inspect
import types
import typing

from almasi import a


class Strict(a.Module):

	# ======================================================================
	# FRAMEWORK METHODS
	# ======================================================================

	# Invoke the original callable only after checking its typed arguments.
	# ----------------------------------------------------------------------
	def __call_method__(self, method, /, *args, **kwargs):
		'''Check a synchronous result or return an awaitable checking its result.'''
		bound      = self._strict_bind(method, *args, **kwargs)
		annotation = bound.signature.return_annotation
		value      = method(*bound.args, **bound.kwargs)

		if inspect.iscoroutinefunction(method):
			result = self._strict_await(value, annotation)
		else:
			self._check_type(value, annotation)
			result = value

		return result

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Check a value without coercion or mutation.
	# ----------------------------------------------------------------------
	@classmethod
	def _check_type(cls, value, annotation):
		'''Raise TypeError if value does not satisfy the supported annotation.'''
		if not cls._strict_match(value, annotation):
			raise TypeError(f'Expected {annotation!r}, got {type(value)!r}')

	# Support concrete classes and common inspectable typing forms.
	# ----------------------------------------------------------------------
	@classmethod
	def _strict_match(cls, value, annotation):
		origin = typing.get_origin(annotation)
		args   = typing.get_args(annotation)

		if annotation is typing.Any:
			result = True
		elif origin in (typing.Union, types.UnionType):
			result = any(cls._strict_match(value, item) for item in args)
		elif origin is typing.Annotated:
			result = cls._strict_match(value, args[0])
		elif origin is typing.Literal:
			result = any(type(value) is type(item) and value == item for item in args)
		elif origin in (list, set, frozenset):
			result = isinstance(value, origin) and (not args or all(cls._strict_match(item, args[0]) for item in value))
		elif origin is dict:
			result = isinstance(value, dict) and (not args or all(
				cls._strict_match(key, args[0]) and cls._strict_match(item, args[1])
				for key, item in value.items()
			))
		elif origin is tuple:
			result = isinstance(value, tuple)

			if result and annotation is not typing.Tuple:
				if len(args) == 2 and args[1] is Ellipsis:
					result = all(cls._strict_match(item, args[0]) for item in value)
				else:
					result = len(value) == len(args) and all(
						cls._strict_match(item, kind) for item, kind in zip(value, args)
					)
		elif origin is a.Resource:
			# A carrier's contents are not inspected or consumed by a type check.
			result = isinstance(value, origin)
		elif isinstance(annotation, type) and origin is None:
			result = isinstance(value, annotation)
		else:
			raise TypeError(f'Unsupported strict annotation: {annotation!r}')

		return result

	# Complete a checked async call without replacing the declared method.
	# ----------------------------------------------------------------------
	async def _strict_await(self, result, annotation):
		value = await result
		self._check_type(value, annotation)

		return value

	# Bind and check all actual arguments, including defaults and variadics.
	# ----------------------------------------------------------------------
	def _strict_bind(self, method, /, *args, **kwargs):
		'''Return checked BoundArguments without executing the method.'''
		signature = self.__get_method_signature__(method)

		for parameter in signature.parameters.values():
			if parameter.annotation is inspect.Parameter.empty:
				raise TypeError(f'Missing annotation: {parameter.name}')

		if signature.return_annotation is inspect.Signature.empty:
			raise TypeError('Missing return annotation')

		bound = signature.bind(*args, **kwargs)
		bound.apply_defaults()

		for name, value in bound.arguments.items():
			parameter = signature.parameters[name]

			if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
				for item in value:
					self._check_type(item, parameter.annotation)
			elif parameter.kind is inspect.Parameter.VAR_KEYWORD:
				for item in value.values():
					self._check_type(item, parameter.annotation)
			else:
				self._check_type(value, parameter.annotation)

		return bound
