# ==============================================================================
# TEST LIBRARIES
# ==============================================================================
# PURPOSE:
# Verify canonical library imports and Git acquisition without authentication.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Loader behavior checks and isolated Git fixtures.
# Delegates: Module publication to Almasi and Git cloning to the Git CLI.
# ==============================================================================

import os
import subprocess
import sys
import tempfile
import types

from concurrent.futures import ThreadPoolExecutor
from unittest          import TestCase
from unittest.mock     import patch

import a
import almasi


class TestLibraries(a.Tester):

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Build a valid source repository with the normal Almasi entry point.
	# ----------------------------------------------------------------------
	@staticmethod
	def _library(directory, name, source=None):
		path = os.path.join(directory, name)
		os.makedirs(os.path.join(path, 'root'), exist_ok=True)

		if source is None:
			source = f'''import a

{name} = a.extend('{name}')
'''

		with open(os.path.join(path, name + '.py'), 'w') as file:
			file.write(source)

		with open(os.path.join(path, 'root', '.gitkeep'), 'w') as file:
			file.write('')

		return path

	# Preserve shared core owners changed by library publication in tests.
	# ----------------------------------------------------------------------
	@staticmethod
	def _ownership():
		return a.Imports.__lib__, a.Tester.__lib__, a.Undefined.__lib__

	# Create a committed local Git repository for clone tests.
	# ----------------------------------------------------------------------
	@classmethod
	def _git_origin(cls, directory, name):
		origin = cls._library(directory, name)

		subprocess.run(['git', 'init', '-q', origin], check=True)
		subprocess.run(['git', '-C', origin, 'add', '.'], check=True)
		subprocess.run([
			'git', '-C', origin, '-c', 'user.email=almasi@example.test',
			'-c', 'user.name=Almasi Test', 'commit', '-q', '-m', 'Fixture'
		], check=True)

		return origin

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Resolve the Singleton as a native Almasi service, not as an alias.
	# ----------------------------------------------------------------------
	@classmethod
	def test_native_service(cls):
		service = a.services.Libraries

		assert isinstance(service, a.Singleton)
		assert service is a.services.Libraries

	# Import through the Python from-list protocol and reuse one library.
	# ----------------------------------------------------------------------
	@classmethod
	def test_qualified_import_reuses_instance(cls):
		ownership = cls._ownership()

		try:
			with tempfile.TemporaryDirectory() as home:
				cls._library(home, 'sample_lib')

				with patch.dict(os.environ, {'ALMASI_LIBRARY_DIR': home}):
					with patch.dict(sys.modules):
						package = __import__('almasi', fromlist=['sample_lib'])
						library = getattr(package, 'sample_lib')

						assert library is getattr(package, 'sample_lib')
						assert sys.modules['almasi.sample_lib'] is library
						assert library.__name__ == 'almasi.sample_lib'
						assert a.services.Libraries.imp('sample_lib') is library
		finally:
			a.Imports.__lib__, a.Tester.__lib__, a.Undefined.__lib__ = ownership
			almasi.__dict__.pop('sample_lib', None)

	# Preserve the official MCP SDK's independent Python module identity.
	# ----------------------------------------------------------------------
	@classmethod
	def test_almasi_mcp_does_not_replace_sdk(cls):
		ownership = cls._ownership()
		sdk       = types.ModuleType('mcp')

		try:
			with tempfile.TemporaryDirectory() as home:
				cls._library(home, 'mcp')

				with patch.dict(os.environ, {'ALMASI_LIBRARY_DIR': home}):
					with patch.dict(sys.modules, {'mcp': sdk}):
						package = __import__('almasi', fromlist=['mcp'])
						library = getattr(package, 'mcp')

						assert __import__('mcp') is sdk
						assert library is not sdk
						assert sys.modules['almasi.mcp'] is library
		finally:
			a.Imports.__lib__, a.Tester.__lib__, a.Undefined.__lib__ = ownership
			almasi.__dict__.pop('mcp', None)

	# Discover the GitHub catalogue without coupling it to local cache state.
	# ----------------------------------------------------------------------
	@classmethod
	def test_list_uses_remote_discovery(cls):
		with tempfile.TemporaryDirectory() as home:
			cls._library(home, 'local_lib')

			with patch.dict(os.environ, {'ALMASI_LIBRARY_DIR': home}):
				with patch.object(type(a.services.Libraries), '_repositories',
								  return_value={'web': 'https://github.com/example/almasi.web.git'}):
					assert a.services.Libraries.list() == ['web']

	# Clone once and reuse a validated checkout.
	# ----------------------------------------------------------------------
	@classmethod
	def test_clone_uses_local_git_and_is_idempotent(cls):
		with tempfile.TemporaryDirectory() as home:
			origin = cls._git_origin(home, 'cloned_lib')
			cache  = os.path.join(home, 'cache')

			with patch.dict(os.environ, {'ALMASI_LIBRARY_DIR': cache}):
				with patch.object(type(a.services.Libraries), '_repositories',
								  return_value={'cloned_lib': origin}):
					path = a.services.Libraries.clone('cloned_lib')

					assert os.path.isfile(os.path.join(path, 'cloned_lib.py'))
					assert path == a.services.Libraries.clone('cloned_lib')
					assert sorted(os.listdir(cache)) == ['cloned_lib']

	# Concurrent Git clones cannot publish a partially downloaded source.
	# ----------------------------------------------------------------------
	@classmethod
	def test_simultaneous_clones_share_checkout(cls):
		with tempfile.TemporaryDirectory() as home:
			origin = cls._git_origin(home, 'parallel_lib')
			cache  = os.path.join(home, 'cache')

			with patch.dict(os.environ, {'ALMASI_LIBRARY_DIR': cache}):
				with patch.object(type(a.services.Libraries), '_repositories',
								  return_value={'parallel_lib': origin}):
					with ThreadPoolExecutor(max_workers=2) as executor:
						paths = list(executor.map(a.services.Libraries.clone, ['parallel_lib'] * 2))

					assert paths[0] == paths[1]
					assert sorted(os.listdir(cache)) == ['parallel_lib']

	# Reject invalid names before constructing a Git command or a module.
	# ----------------------------------------------------------------------
	@classmethod
	def test_invalid_names_do_not_resolve(cls):
		with TestCase().assertRaises(ValueError):
			a.services.Libraries.imp('../outside')

		with TestCase().assertRaises(ValueError):
			a.services.Libraries.clone('NotSnakeCase')

	# Failed source execution leaves no falsely published library module.
	# ----------------------------------------------------------------------
	@classmethod
	def test_failed_import_cleans_publication(cls):
		with tempfile.TemporaryDirectory() as home:
			cls._library(home, 'broken_lib', '''raise RuntimeError('broken source')
''')

			with patch.dict(os.environ, {'ALMASI_LIBRARY_DIR': home}):
				with patch.dict(sys.modules):
					with TestCase().assertRaisesRegex(RuntimeError, 'broken source'):
						a.services.Libraries.imp('broken_lib')

					assert 'almasi.broken_lib' not in sys.modules


if __name__ == '__main__':
	TestLibraries.run()
