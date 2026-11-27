# ==============================================================================
# STRICT
# ==============================================================================
# PURPOSE:
# Check explicitly invoked Python methods against their declared types.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Binding and enforcement of typed method contracts.
# Delegates: Value matching to Annotation and execution to the original method.
# ==============================================================================

import inspect

from almasi import a


class Strict(a.Module):

	# ======================================================================
	# FRAMEWORK METHODS
	# ======================================================================

	# Invoke the original callable only after checking its typed arguments.
	# ----------------------------------------------------------------------
	def __call_method__(self, method, /, *args, **kwargs):
		'''Invoke a method with explicit runtime argument and result checks.'''
		return self._call_method(method, self.__get_method_signature__(method), *args, **kwargs)

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Check a value without coercion or mutation.
	# ----------------------------------------------------------------------
	@staticmethod
	def _check_type(value, annotation):
		'''Raise TypeError if value does not satisfy the supported annotation.'''
		if not a.Annotation(annotation).matches(value):
			raise TypeError(f'Expected {annotation!r}, got {type(value)!r}')

	# Complete a checked async call without replacing the declared method.
	# ----------------------------------------------------------------------
	async def _strict_await(self, result, annotation):
		value = await result
		self._check_type(value, annotation)

		return value

	# Bind and check all actual arguments, including defaults and variadics.
	# ----------------------------------------------------------------------
	def _strict_bind(self, signature, /, *args, **kwargs):

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

	# Execute a previously reflected signature without resolving it again.
	# ----------------------------------------------------------------------
	def _call_method(self, method, signature, /, *args, **kwargs):
		bound      = self._strict_bind(signature, *args, **kwargs)
		annotation = signature.return_annotation
		value      = method(*bound.args, **bound.kwargs)

		if inspect.iscoroutinefunction(method):
			result = self._strict_await(value, annotation)
		else:
			self._check_type(value, annotation)
			result = value

		return result
