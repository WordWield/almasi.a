# ==============================================================================
# SINGLETON
# ==============================================================================
# PURPOSE:
# Maintain one instance and one successful initialization per concrete class.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Singleton identity and the initialization guard.
# Delegates: Namespace lookup to Module and initialization to subclasses.
# ==============================================================================

import types

from .module import Module


class Singleton(Module):

	__instance__     = None
	_is_initialized  = True
	_is_initializing = False

	# ======================================================================
	# FRAMEWORK METHODS
	# ======================================================================

	# Create one concrete service instance with its own initialization state.
	# ----------------------------------------------------------------------
	def __new__(cls):
		instance = cls.__dict__.get('__instance__')

		if instance is None:
			instance   = super().__new__(cls)
			initialize = getattr(cls, 'initialize', None)

			instance._initialize      = initialize
			instance._is_initialized  = initialize is None
			instance._is_initializing = False
			instance.initialize       = types.MethodType(cls._initialize, instance)

			cls.__instance__ = instance

		return instance

	# Use the service class when a namespace instance appears as a base.
	# ----------------------------------------------------------------------
	def __mro_entries__(self, bases):
		return (type(self),)

	# Treat the service instance as its class in isinstance() checks.
	# ----------------------------------------------------------------------
	def __instancecheck__(self, instance):
		return isinstance(instance, type(self))

	# Treat the service instance as its class in issubclass() checks.
	# ----------------------------------------------------------------------
	def __subclasscheck__(self, subclass):
		return issubclass(subclass, type(self))

	# Allow missing-attribute resolution only during or after initialization.
	# ----------------------------------------------------------------------
	def __getattr__(self, name):
		if self._is_initialized or self._is_initializing:
			result = super().__getattr__(name)
		else:
			raise RuntimeError(f'Singleton `{self.__class__.__name__}` is not initialized. Call `initialize()` before use.')

		return result

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Invoke the original initializer once, allowing retries after failure.
	# ----------------------------------------------------------------------
	def _initialize(self, *args, **kwargs):
		initialize = self._initialize

		if not self._is_initialized:
			if initialize is not None:
				self._is_initializing = True

				try:
					initialize(self, *args, **kwargs)
					self._is_initialized = True
				finally:
					self._is_initializing = False
		else:
			raise RuntimeError(f'Singleton `{self.__class__.__name__}` is already initialized')
