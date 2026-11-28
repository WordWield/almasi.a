import inspect
import sys
import typing

from .function import Function
# from .events   import Events


# ==============================================================================
# CLASS MODULE META
# ==============================================================================
class ModuleMeta(type):

	# ======================================================================
	# REFLECTION METHODS
	# ======================================================================

	# Get module object
	# ----------------------------------------------------------------------
	@classmethod
	def module(mcls, namespace):
		return sys.modules.get(namespace.get('__module__'))

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

		if class_name is not None:
			return short_name == class_name

		return False

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
class Module(metaclass=ModuleMeta):

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
	# REFLECTION METHODS
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

	# Describe method inputs and output without exposing inspect objects.
	# ----------------------------------------------------------------------
	@staticmethod
	def __get_method_signature__(method, localns=None, skip_owner=False):
		result = getattr(method, '__signature__', None)

		if not isinstance(result, dict):
			signature  = inspect.signature(method)
			hints      = typing.get_type_hints(method, localns=localns, include_extras=True)
			parameters = tuple(signature.parameters.values())[1 if skip_owner else 0:]
			inputs     = {}

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

			output = {}
			annotation = hints.get('return', signature.return_annotation)

			if annotation is not inspect.Signature.empty:
				output['type'] = annotation

			result = {'inputs': inputs, 'output': output}

		return result

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
