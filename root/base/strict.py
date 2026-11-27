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
	# PRIVATE METHODS
	# ======================================================================

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
			result = isinstance(value, origin) and all(cls._strict_match(item, args[0]) for item in value)
		elif origin is dict:
			result = isinstance(value, dict) and all(
				cls._strict_match(key, args[0]) and cls._strict_match(item, args[1])
				for key, item in value.items()
			)
		elif origin is tuple:
			result = isinstance(value, tuple)

			if result:
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
		self.strict_check(value, annotation)

		return value

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Check a value without coercion or mutation.
	# ----------------------------------------------------------------------
	@classmethod
	def strict_check(cls, value, annotation):
		'''Raise TypeError if value does not satisfy the supported annotation.'''
		if not cls._strict_match(value, annotation):
			raise TypeError(f'Expected {annotation!r}, got {type(value)!r}')

	# Resolve the real callable signature without replacing its declaration.
	# ----------------------------------------------------------------------
	@staticmethod
	def strict_signature(method):
		'''Return a resolved Signature, requiring parameter and result annotations.'''
		signature  = inspect.signature(method)
		hints      = typing.get_type_hints(method, include_extras=True)
		parameters = []

		for parameter in signature.parameters.values():
			if parameter.name in hints:
				parameters.append(parameter.replace(annotation=hints[parameter.name]))
			else:
				raise TypeError(f'Missing annotation: {parameter.name}')

		if 'return' not in hints:
			raise TypeError('Missing return annotation')

		return signature.replace(parameters=parameters, return_annotation=hints['return'])

	# Bind and check all actual arguments, including defaults and variadics.
	# ----------------------------------------------------------------------
	def strict_bind(self, method, *args, **kwargs):
		'''Return checked BoundArguments without executing the method.'''
		signature = self.strict_signature(method)
		bound     = signature.bind(*args, **kwargs)
		bound.apply_defaults()

		for name, value in bound.arguments.items():
			parameter = signature.parameters[name]

			if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
				for item in value:
					self.strict_check(item, parameter.annotation)
			elif parameter.kind is inspect.Parameter.VAR_KEYWORD:
				for item in value.values():
					self.strict_check(item, parameter.annotation)
			else:
				self.strict_check(value, parameter.annotation)

		return bound

	# Invoke the original callable only after checking its typed arguments.
	# ----------------------------------------------------------------------
	def strict_call(self, method, *args, **kwargs):
		'''Check a synchronous result or return an awaitable checking its result.'''
		bound      = self.strict_bind(method, *args, **kwargs)
		annotation = bound.signature.return_annotation
		value      = method(*bound.args, **bound.kwargs)

		if inspect.iscoroutinefunction(method):
			result = self._strict_await(value, annotation)
		else:
			self.strict_check(value, annotation)
			result = value

		return result
