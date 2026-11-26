import hashlib
import os
import sys
import importlib.util


class Imports:

	__fork_codes__ = {}

	# Give each fork its own module identity while retaining legacy keys.
	# ----------------------------------------------------------------------
	@classmethod
	def module_key(cls, lib, path):
		path = os.path.realpath(path)
		key  = f'{path}#fork-{id(lib)}' if lib.__dict__.get('__fork_source__') is not None else path
		return key

	# Record the identity of the executed source; forks may reuse compiled code.
	# ----------------------------------------------------------------------
	@classmethod
	def _execute_module(cls, module, path, share_code=False):
		cached = None

		if share_code:
			stat   = os.stat(path)
			stamp  = (stat.st_mtime_ns, stat.st_size)
			cached = cls.__fork_codes__.get(path)

		if cached is not None and cached[0] == stamp:
			_, code, source_hash = cached
		else:
			with open(path, 'rb') as source:
				content = source.read()

			code        = compile(content, path, 'exec')
			source_hash = hashlib.sha256(content).digest()

			if share_code:
				cls.__fork_codes__[path] = (stamp, code, source_hash)

		module.__source_hash__ = source_hash
		exec(code, module.__dict__)

	# Compare the current source with the exact version executed by the loader.
	# ----------------------------------------------------------------------
	@classmethod
	def has_source_changed(cls, module):
		with open(module.__file__, 'rb') as source:
			changed = hashlib.sha256(source.read()).digest() != module.__source_hash__

		return changed

	# Discard source code after a known filesystem mutation.
	# ----------------------------------------------------------------------
	@classmethod
	def invalidate_code(cls, path):
		cls.__fork_codes__.pop(os.path.realpath(path), None)

	# Load under an explicit name when supplied; otherwise preserve file identity.
	# ----------------------------------------------------------------------
	@classmethod
	def load_module(
		cls,
		lib,
		path,
		route       = None,
		namespace   = None,
		module_name = None
	):
		path   = os.path.realpath(path)
		key    = module_name if module_name is not None else cls.module_key(lib, path)
		module = sys.modules.get(key)

		if module is None:
			spec   = importlib.util.spec_from_file_location(key, path)
			module = importlib.util.module_from_spec(spec)

			module.__lib__   = lib
			module.__route__ = route
			module.__mtime__ = os.path.getmtime(path)
			module.__dict__['UNDEFINED'] = lib.Undefined

			if lib.__dict__.get('__fork_source__') is not None:
				module.__dict__['__builtins__'] = lib.__fork_builtins__

			sys.modules[key] = module

			try:
				cls._execute_module(module, path, share_code=lib.__dict__.get('__fork_source__') is not None)
			except Exception:
				sys.modules.pop(key, None)
				raise

		return module

	# Stage fresh source without changing the published Python module.
	# Read the source directly so unchanged file timestamps cannot reuse bytecode.
	# ----------------------------------------------------------------------
	@classmethod
	def prepare_module(cls, lib, path, route):
		path     = os.path.realpath(path)
		key      = cls.module_key(lib, path)
		previous = sys.modules.get(key)
		spec     = importlib.util.spec_from_file_location(key, path)
		module   = importlib.util.module_from_spec(spec)

		module.__lib__   = lib
		module.__route__ = route
		module.__mtime__ = os.path.getmtime(path)
		module.__dict__['UNDEFINED'] = lib.Undefined

		if lib.__dict__.get('__fork_source__') is not None:
			module.__dict__['__builtins__'] = lib.__fork_builtins__

		sys.modules[key] = module

		try:
			cls._execute_module(module, path)
		finally:
			if previous is not None:
				sys.modules[key] = previous
			else:
				sys.modules.pop(key, None)

		return module

	# Get class
	# ----------------------------------------------------------------------
	@classmethod
	def get_class(cls, lib, class_name, path, route=None, namespace=None):
		file_path = path
		
		if not path.endswith('.py'):
			file_name = lib.String.camel_to_snake(class_name) + '.py'
			file_path = os.path.realpath(os.path.join(path, file_name))

		module = cls.load_module(lib, file_path, route, namespace)
		return getattr(module, class_name)
