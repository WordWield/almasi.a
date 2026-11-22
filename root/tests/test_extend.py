# ==============================================================================
# TEST LIBRARY EXTENSION
# ==============================================================================
# Verify canonical identity, inherited loading, and explicit initialization.
# ==============================================================================

import importlib
import os
import runpy
import sys
import tempfile

import almasi

from contextlib    import contextmanager
from unittest      import TestCase
from unittest.mock import patch


class TestExtend(almasi.Tester):

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Isolate module publication and restore shared library ownership.
	# ----------------------------------------------------------------------
	@staticmethod
	@contextmanager
	def _runtime():
		state = almasi.Imports.__lib__, almasi.Tester.__lib__, almasi.Undefined.__lib__

		try:
			with tempfile.TemporaryDirectory() as root, patch.dict(sys.modules), patch.object(sys, 'path', list(sys.path)):
				yield root
		finally:
			almasi.Imports.__lib__, almasi.Tester.__lib__, almasi.Undefined.__lib__ = state

	# Write an importable library with its own filesystem root.
	# ----------------------------------------------------------------------
	@staticmethod
	def _source(root, name, code):
		directory = os.path.join(root, name)
		os.makedirs(os.path.join(directory, 'root'))
		path = os.path.join(directory, f'{name}.py')

		with open(path, 'w') as file:
			file.write(code)

		return directory

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Preserve native imports, MRO, source ownership, and service identity.
	# ----------------------------------------------------------------------
	@classmethod
	def test_extend_preserves_library_resolution(cls):
		with cls._runtime() as root:
			parent_dir = cls._source(root, 'extend_parent', '''import almasi

extend_parent = almasi.extend('extend_parent')
''')
			child_dir  = cls._source(root, 'extend_child', '''import extend_parent

extend_child = extend_parent.extend('extend_child')
''')
			os.makedirs(os.path.join(parent_dir, 'root', 'api'))

			with open(os.path.join(parent_dir, 'root', 'api', 'shared.py'), 'w') as file:
				file.write('import almasi\n\nclass Shared(almasi.Singleton):\n\tpass\n')

			sys.path[:0] = [child_dir, parent_dir]
			child  = importlib.import_module('extend_child')
			parent = importlib.import_module('extend_parent')

			assert sys.modules['extend_parent'] is parent
			assert sys.modules['extend_child'] is child
			assert type(child).__bases__ == (type(parent),)
			assert child.__path__ == os.path.join(os.path.realpath(child_dir), 'root')
			assert parent.api.Shared is child.api.Shared
			assert sys.modules[type(child.api.Shared).__module__].__lib__ is parent

	# Import inherited Python definitions and prefer local files on collision.
	# ----------------------------------------------------------------------
	@classmethod
	def test_import_python_inherited(cls):
		with cls._runtime() as root:
			parent_dir = cls._source(root, 'import_parent', '''import almasi

import_parent = almasi.extend('import_parent')
''')
			child_dir = cls._source(root, 'import_child', '''import import_parent

import_child = import_parent.extend('import_child')
''')
			parent_schemas = os.path.join(parent_dir, 'root', 'schemas')
			child_schemas  = os.path.join(child_dir, 'root', 'schemas')
			os.makedirs(parent_schemas)
			os.makedirs(child_schemas)

			for name, value in (('shared.py', 11), ('preferred.py', 12)):
				with open(os.path.join(parent_schemas, name), 'w') as source:
					source.write(f'VALUE = {value}\n')

			with open(os.path.join(child_schemas, 'preferred.py'), 'w') as source:
				source.write('VALUE = 22\n')

			sys.path[:0] = [child_dir, parent_dir]
			child  = importlib.import_module('import_child')
			parent = importlib.import_module('import_parent')

			shared    = child.schemas.import_python('shared')
			preferred = child.schemas.import_python('preferred.py')

			assert shared.VALUE == 11
			assert shared.__lib__ is parent
			assert shared.__route__ == 'import_child.schemas.shared'
			assert preferred.VALUE == 22
			assert preferred.__lib__ is child
			assert preferred.__route__ == 'import_child.schemas.preferred'
			assert child.schemas.import_python('shared.py') is shared

	# Reject legacy class declarations; library creation is explicit.
	# ----------------------------------------------------------------------
	@classmethod
	def test_extend_rejects_class_declaration(cls):
		with cls._runtime() as root:
			directory = cls._source(root, 'extend_legacy', '''import almasi

class ExtendLegacy(almasi.A):
\tpass
''')
			sys.path.insert(0, directory)
			with TestCase().assertRaisesRegex(TypeError, 'almasi.extend'):
				importlib.import_module('extend_legacy')

	# Keep __main__ intact and run entry-point code only for direct execution.
	# ----------------------------------------------------------------------
	@classmethod
	def test_extend_from_main(cls):
		with cls._runtime() as root:
			app_dir = cls._source(root, 'extend_app', '''import almasi

extend_app = almasi.extend('extend_app')

if __name__ == '__main__':
\textend_app.started = True
''')
			main   = sys.modules['__main__']
			result = runpy.run_path(os.path.join(app_dir, 'extend_app.py'), run_name='__main__')
			app    = result['extend_app']

			assert sys.modules['__main__'] is main
			assert sys.modules['extend_app'] is app
			assert app.started is True
			assert app.__name__ == 'extend_app'

	# Reject names unrelated to the source module.
	# ----------------------------------------------------------------------
	@classmethod
	def test_extend_rejects_mismatched_source(cls):
		with cls._runtime() as root:
			directory = cls._source(root, 'extend_named', '''import almasi

extend_named = almasi.extend('another_name')
''')
			sys.path.insert(0, directory)
			error = None

			try:
				importlib.import_module('extend_named')
			except ValueError as exception:
				error = str(exception)

			assert error is not None
			assert 'must match' in error

	# Reject noncanonical snake_case names before publishing anything.
	# ----------------------------------------------------------------------
	@classmethod
	def test_extend_rejects_invalid_name(cls):
		with cls._runtime() as root:
			directory = cls._source(root, 'extend_invalid', '''import almasi

extend_invalid = almasi.extend('InvalidName')
''')
			sys.path.insert(0, directory)
			error = None

			try:
				importlib.import_module('extend_invalid')
			except ValueError as exception:
				error = str(exception)

			assert error is not None
			assert 'Invalid library name' in error
