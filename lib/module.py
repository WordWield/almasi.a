# ==============================================================================
# MODULE
# ==============================================================================
# PURPOSE:
# Provide Almasi module identity, application context and instance behavior.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Publishing source metadata and module instance behavior.
# Delegates: Class and method reflection to ReflectionMeta and Reflection.
# ==============================================================================

import sys

from .function        import Function
from .reflection      import Reflection
from .reflection_meta import ReflectionMeta
# from .events   import Events


# ==============================================================================
# CLASS MODULE META
# ==============================================================================
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


# ==============================================================================
# CLASS MODULE
# ==============================================================================
class Module(Reflection, metaclass=ModuleMeta):

	_instance_counter = 0

	# ======================================================================
	# FRAMEWORK METHODS
	# ======================================================================

	# Read the currently selected application without binding it at import time.
	# ----------------------------------------------------------------------
	@property
	def __app__(self):
		return sys.modules['almasi.a'].__app__

	# Using new to avoid having to call super().__init__() everywhere
	# ----------------------------------------------------------------------
	def __new__(cls, *args, **kwargs):
		self = super().__new__(cls)

		Module._instance_counter += 1
		self.__instance_id__ = Module._instance_counter

		return self

	# Intercept method access to inject event hooks
	# ----------------------------------------------------------------------
	def __getattr__(self, name):
		from .events import Events
		attr = object.__getattribute__(self, name)

		if not name.startswith('_') and callable(attr) and Events.has(attr):
			def wrapped(*args, **kwargs):
				Events.trigger(attr)
				fn = Function(attr)
				return fn(*args, **kwargs)

			return wrapped

		return attr

	# String representation
	# ----------------------------------------------------------------------
	def __repr__(cls):
		text  = cls.__class__.__name__
		route = getattr(cls, '__route__', None)

		if isinstance(route, str):
			text = route

		return f'<Module \'{text}\'>'

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Attach callback to foreign method execution
	# ----------------------------------------------------------------------
	# def on(self, foreign_method, own_method):
	# 	Events.on(foreign_method, own_method)

	# Namespaced debug print
	# ----------------------------------------------------------------------
	def print(self, *args, **kwargs):
		gray         = '\033[38;5;242m'
		reset        = '\033[0m'

		if getattr(self, 'verbose', False):
			print(f'{gray}{self.__route__}:{reset}', *args, **kwargs)

	# Note
	# ----------------------------------------------------------------------
	def note(self, *args, **kwargs):
		word_color  = '\033[38;5;39m'
		reset       = '\033[0m'

		args = list(args)
		args.insert(0, f'ℹ️ {word_color}Note:{reset}')
		return self.print(*args, **kwargs)

	# Warning
	# ----------------------------------------------------------------------
	def warn(self, *args, **kwargs):
		word_color  = '\033[38;5;172m'
		reset       = '\033[0m'

		args = list(args)
		args.insert(0, f'⚠️{word_color} WARNING:{reset}')
		return self.print(*args, **kwargs)

	# Error
	# ----------------------------------------------------------------------
	def error(self, *args, **kwargs):
		word_color  = '\033[38;5;210m'
		reset       = '\033[0m'

		args = list(args)
		args.insert(0, f'🚫{word_color}ERROR:{reset}')
		self.print(*args, **kwargs)
		exit(0)
