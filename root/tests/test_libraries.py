# ==============================================================================
# TEST LIBRARIES
# ==============================================================================
# Verify on-demand library imports and isolated local Git acquisition.
# ==============================================================================

import os
import subprocess
import sys
import tempfile
import types

from unittest      import TestCase
from unittest.mock import patch

import a
import almasi


class TestLibraries(a.Tester):

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Create a source library with the ordinary Almasi entry-point contract.
	# ----------------------------------------------------------------------
	@staticmethod
	def _library(directory, name, source=None):
		path = os.path.join(directory, name)
		os.makedirs(os.path.join(path, 'root'), exist_ok=True)

		with open(os.path.join(path, name + '.py'), 'w') as file:
			file.write(source or f"import a\n\n{name} = a.extend('{name}')\n")

		with open(os.path.join(path, 'root', '.gitkeep'), 'w') as file:
			file.write('')

		return path

	# Restore the shared core ownership changed by library publication.
	# ----------------------------------------------------------------------
	@staticmethod
	def _ownership():
		return a.Imports.__lib__, a.Tester.__lib__, a.Undefined.__lib__

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Expose the same Singleton from both the core and the import namespace.
	# ----------------------------------------------------------------------
	@classmethod
	def test_namespace_shares_service(cls):
		assert almasi.Libraries is a.Libraries
		assert a.Libraries is a.Libraries

	# Import locally once and reuse the canonical published library instance.
	# ----------------------------------------------------------------------
	@classmethod
	def test_qualified_import_reuses_instance(cls):
		ownership = cls._ownership()

		try:
			with tempfile.TemporaryDirectory() as home:
				cls._library(home, 'sample_lib')

				with patch.dict(os.environ, {'ALMASI_LIBRARY_DIR': home}):
					with patch.dict(sys.modules):
						from almasi import sample_lib
						from almasi import sample_lib as again

						assert sample_lib is again
						assert sys.modules['almasi.sample_lib'] is sample_lib
						assert sample_lib.__name__ == 'almasi.sample_lib'
						assert a.Libraries.imp('sample_lib') is sample_lib
		finally:
			a.Imports.__lib__, a.Tester.__lib__, a.Undefined.__lib__ = ownership
			almasi.__dict__.pop('sample_lib', None)

	# Let a qualified Almasi MCP library coexist with a top-level MCP SDK.
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
						from almasi import mcp
						import mcp as imported_sdk

						assert imported_sdk is sdk
						assert mcp is not sdk
						assert sys.modules['almasi.mcp'] is mcp
		finally:
			a.Imports.__lib__, a.Tester.__lib__, a.Undefined.__lib__ = ownership
			almasi.__dict__.pop('mcp', None)

	# Combine local and remote names without maintaining a second registry.
	# ----------------------------------------------------------------------
	@classmethod
	def test_list_merges_local_and_discoverable(cls):
		with tempfile.TemporaryDirectory() as home:
			cls._library(home, 'local_lib')

			with patch.dict(os.environ, {'ALMASI_LIBRARY_DIR': home}):
				with patch.object(type(a.Libraries), '_remote_repositories', return_value={'web': 'https://github.com/example/almasi.web.git'}):
					assert a.Libraries.list() == ['local_lib', 'web']

	# Git clone must finish and validate before publishing its destination.
	# ----------------------------------------------------------------------
	@classmethod
	def test_clone_uses_local_git_and_is_idempotent(cls):
		with tempfile.TemporaryDirectory() as home:
			origin = cls._library(home, 'cloned_lib')
			cache  = os.path.join(home, 'cache')

			subprocess.run(['git', 'init', '-q', origin], check=True)
			subprocess.run(['git', '-C', origin, 'add', '.'], check=True)
			subprocess.run([
				'git', '-C', origin, '-c', 'user.email=almasi@example.test',
				'-c', 'user.name=Almasi Test', 'commit', '-q', '-m', 'Fixture'
			], check=True)

			with patch.dict(os.environ, {'ALMASI_LIBRARY_DIR': cache}):
				with patch.object(type(a.Libraries), '_remote_repositories', return_value={'cloned_lib': origin}):
					path = a.Libraries.clone('cloned_lib')

					assert os.path.isfile(os.path.join(path, 'cloned_lib.py'))
					assert path == a.Libraries.clone('cloned_lib')
					assert sorted(os.listdir(cache)) == ['cloned_lib']

	# Reject unexpected names before constructing a Git URL or importing.
	# ----------------------------------------------------------------------
	@classmethod
	def test_invalid_names_do_not_resolve(cls):
		with TestCase().assertRaises(ValueError):
			a.Libraries.imp('../outside')

		with TestCase().assertRaises(ValueError):
			a.Libraries.clone('NotSnakeCase')

	# Keep failed entry-point execution out of canonical Python modules.
	# ----------------------------------------------------------------------
	@classmethod
	def test_failed_import_cleans_publication(cls):
		with tempfile.TemporaryDirectory() as home:
			cls._library(home, 'broken_lib', "raise RuntimeError('broken source')\n")

			with patch.dict(os.environ, {'ALMASI_LIBRARY_DIR': home}):
				with patch.dict(sys.modules):
					with TestCase().assertRaisesRegex(RuntimeError, 'broken source'):
						a.Libraries.imp('broken_lib')

					assert 'almasi.broken_lib' not in sys.modules


if __name__ == '__main__':
	TestLibraries.run()
