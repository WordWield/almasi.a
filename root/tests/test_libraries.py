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

from contextlib        import redirect_stderr, redirect_stdout
from io                import StringIO
from unittest          import TestCase
from unittest.mock     import patch

import almasi


class TestLibraries(almasi.Tester):

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Build a valid source repository with the normal Almasi entry point.
	# ----------------------------------------------------------------------
	@staticmethod
	def _library(directory, name, source=None):
		path = os.path.join(directory, 'almasi.' + name)
		os.makedirs(os.path.join(path, 'root'), exist_ok=True)

		if source is None:
			source = f'''import almasi

{name} = almasi.extend('{name}')
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
		return almasi.Imports.__lib__, almasi.Tester.__lib__, almasi.Undefined.__lib__

	# Commit test fixtures without invoking user Git hooks or signing.
	# ----------------------------------------------------------------------
	@staticmethod
	def _git_commit(directory, message):
		subprocess.run([
			'git', '-C', directory,
			'-c', f'core.hooksPath={os.devnull}',
			'-c', 'commit.gpgSign=false',
			'-c', 'user.email=almasi@example.test',
			'-c', 'user.name=Almasi Test',
			'commit', '-q', '-m', message
		], check=True, capture_output=True, text=True)

	# Create a committed local Git repository for clone tests.
	# ----------------------------------------------------------------------
	@classmethod
	def _git_origin(cls, directory, name):
		origin  = cls._library(directory, name)
		git_dir = origin + '.git'
		os.rename(origin, git_dir)

		subprocess.run(
			['git', 'init', '-q', git_dir],
			check=True, capture_output=True, text=True
		)
		subprocess.run(
			['git', '-C', git_dir, 'add', '.'],
			check=True, capture_output=True, text=True
		)
		cls._git_commit(git_dir, 'Fixture')

		return git_dir

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Resolve the Singleton as a native Almasi service, not as an alias.
	# ----------------------------------------------------------------------
	@classmethod
	def test_native_service(cls):
		service = almasi.services.Libraries

		assert isinstance(service, almasi.Singleton)
		assert service is almasi.services.Libraries

	# Import through the Python from-list protocol and reuse one library.
	# ----------------------------------------------------------------------
	@classmethod
	def test_qualified_import_reuses_instance(cls):
		ownership = cls._ownership()

		try:
			with tempfile.TemporaryDirectory() as home:
				cls._library(home, 'sample_lib')

				with patch.dict(os.environ, {'ALMASI_PATH': home}):
					with patch.dict(sys.modules):
						package = __import__('almasi', fromlist=['sample_lib'])
						library = getattr(package, 'sample_lib')

						assert library is getattr(package, 'sample_lib')
						assert sys.modules['almasi.sample_lib'] is library
						assert library.__name__ == 'almasi.sample_lib'
						assert almasi.services.Libraries.imp('sample_lib') is library
		finally:
			almasi.Imports.__lib__, almasi.Tester.__lib__, almasi.Undefined.__lib__ = ownership
			almasi.__dict__.pop('sample_lib', None)

	# Bind qualified Almasi imports to a fork without changing the published library.
	# ----------------------------------------------------------------------
	@classmethod
	def test_qualified_fromlist_import_uses_fork(cls):
		ownership = cls._ownership()

		try:
			with tempfile.TemporaryDirectory() as home:
				origin = cls._library(home, 'fork_sample')

				with open(os.path.join(origin, 'root', 'item.py'), 'w') as stream:
					stream.write('''from almasi import fork_sample


class Item(fork_sample.Module):

	def owner(self):
		return fork_sample
''')

				with patch.dict(os.environ, {'ALMASI_PATH': home}):
					with patch.dict(sys.modules):
						library = getattr(__import__('almasi', fromlist=['fork_sample']), 'fork_sample')
						alice   = library.fork('alice')
						bob     = library.fork('bob')

						assert library.Item().owner() is library
						assert alice.Item().owner() is alice
						assert bob.Item().owner() is bob
						assert sys.modules['almasi.fork_sample'] is library
		finally:
			almasi.Imports.__lib__, almasi.Tester.__lib__, almasi.Undefined.__lib__ = ownership
			almasi.__dict__.pop('fork_sample', None)

	# Preserve the official MCP SDK's independent Python module identity.
	# ----------------------------------------------------------------------
	@classmethod
	def test_almasi_mcp_does_not_replace_sdk(cls):
		ownership = cls._ownership()
		sdk       = types.ModuleType('mcp')

		try:
			with tempfile.TemporaryDirectory() as home:
				cls._library(home, 'mcp')

				with patch.dict(os.environ, {'ALMASI_PATH': home}):
					with patch.dict(sys.modules, {'mcp': sdk}):
						package = __import__('almasi', fromlist=['mcp'])
						library = getattr(package, 'mcp')

						assert __import__('mcp') is sdk
						assert library is not sdk
						assert sys.modules['almasi.mcp'] is library
		finally:
			almasi.Imports.__lib__, almasi.Tester.__lib__, almasi.Undefined.__lib__ = ownership
			almasi.__dict__.pop('mcp', None)

	# Build Git origins from the configured source base.
	# ----------------------------------------------------------------------
	@classmethod
	def test_custom_git_source(cls):
		with tempfile.TemporaryDirectory() as origin:
			with patch.dict(os.environ, {'ALMASI_GIT_BASE': origin}):
				assert almasi.services.Libraries.get_url('web') == f'{origin}/almasi.web.git'

	# A suffix determines the checkout path and cloned state.
	# ----------------------------------------------------------------------
	@classmethod
	def test_is_cloned(cls):
		with tempfile.TemporaryDirectory() as home:
			with patch.dict(os.environ, {'ALMASI_PATH': home}):
				assert not almasi.services.Libraries.is_cloned('sample_lib')
				cls._library(home, 'sample_lib')
				assert almasi.services.Libraries.is_cloned('sample_lib')
				assert almasi.services.Libraries.get_path('sample_lib') == os.path.join(home, 'almasi.sample_lib')

	# Clone an actual local Git origin once and reuse the checkout.
	# ----------------------------------------------------------------------
	@classmethod
	def test_clone_uses_local_git_and_is_idempotent(cls):
		with tempfile.TemporaryDirectory() as home:
			cls._git_origin(home, 'cloned_lib')
			cache = os.path.join(home, 'cache')

			with patch.dict(os.environ, {
				'ALMASI_PATH'     : cache,
				'ALMASI_GIT_BASE' : home,
			}):
				path = almasi.services.Libraries.clone('cloned_lib')

				assert os.path.isfile(os.path.join(path, 'cloned_lib.py'))
				assert path == almasi.services.Libraries.clone('cloned_lib')
				assert sorted(os.listdir(cache)) == ['almasi.cloned_lib']

	# Load the newest committed source only before its first use in a process.
	# ----------------------------------------------------------------------
	@classmethod
	def test_import_pulls_updated_source_once(cls):
		ownership = cls._ownership()

		try:
			with tempfile.TemporaryDirectory() as home:
				origin = cls._git_origin(home, 'pull_lib')
				cache  = os.path.join(home, 'cache')

				with patch.dict(os.environ, {
					'ALMASI_PATH'     : cache,
					'ALMASI_GIT_BASE' : home,
				}):
					with patch.dict(sys.modules):
						almasi.services.Libraries.imp('pull_lib')

					with open(os.path.join(origin, 'pull_lib.py'), 'a') as source:
						source.write('''\npull_lib.revision = 'updated'\n''')

					subprocess.run(
						['git', '-C', origin, 'add', '.'],
						check=True, capture_output=True, text=True
					)
					cls._git_commit(origin, 'Update')

					log    = StringIO()
					stdout = StringIO()

					with redirect_stdout(stdout), redirect_stderr(log):
						with patch.dict(sys.modules):
							library = almasi.services.Libraries.imp('pull_lib')
							assert library.revision == 'updated'
							assert almasi.services.Libraries.imp('pull_lib') is library

					assert not stdout.getvalue(), repr(stdout.getvalue())
					assert log.getvalue().count('✔ almasi.pull_lib: Checking for updates') == 1, repr(log.getvalue())
		finally:
			almasi.Imports.__lib__, almasi.Tester.__lib__, almasi.Undefined.__lib__ = ownership
			almasi.__dict__.pop('pull_lib', None)

	# Continue with committed local source when a remote Git update fails.
	# ----------------------------------------------------------------------
	@classmethod
	def test_import_uses_local_source_when_pull_fails(cls):
		ownership = cls._ownership()

		try:
			with tempfile.TemporaryDirectory() as home:
				cls._git_origin(home, 'offline_lib')
				cache = os.path.join(home, 'cache')

				with patch.dict(os.environ, {
					'ALMASI_PATH'     : cache,
					'ALMASI_GIT_BASE' : home,
				}):
					checkout = almasi.services.Libraries.clone('offline_lib')
					subprocess.run([
						'git', '-C', checkout, 'remote', 'set-url', 'origin',
						os.path.join(home, 'not-found')
					], check=True)

					log = StringIO()

					with redirect_stderr(log):
						with patch.dict(sys.modules):
							library = almasi.services.Libraries.imp('offline_lib')
							assert library.__name__ == 'almasi.offline_lib'

					assert '⚠️ almasi.offline_lib: using local version' in log.getvalue()
		finally:
			almasi.Imports.__lib__, almasi.Tester.__lib__, almasi.Undefined.__lib__ = ownership
			almasi.__dict__.pop('offline_lib', None)

	# A previously acquired checkout remains usable without a Git executable.
	# ----------------------------------------------------------------------
	@classmethod
	def test_import_uses_local_source_without_git(cls):
		ownership = cls._ownership()

		try:
			with tempfile.TemporaryDirectory() as home:
				cls._git_origin(home, 'no_git_lib')
				cache = os.path.join(home, 'cache')

				with patch.dict(os.environ, {
					'ALMASI_PATH'     : cache,
					'ALMASI_GIT_BASE' : home
				}):
					almasi.services.Libraries.clone('no_git_lib')
					empty_path = os.path.join(home, 'empty')
					os.mkdir(empty_path)
					log = StringIO()

					with patch.dict(os.environ, {'PATH': empty_path}):
						with redirect_stderr(log), patch.dict(sys.modules):
							library = almasi.services.Libraries.imp('no_git_lib')
							assert library.__name__ == 'almasi.no_git_lib'

					assert 'using local version' in log.getvalue()
		finally:
			almasi.Imports.__lib__, almasi.Tester.__lib__, almasi.Undefined.__lib__ = ownership
			almasi.__dict__.pop('no_git_lib', None)

	# Recheck requirements for each new process, but not each repeated import.
	# ----------------------------------------------------------------------
	@classmethod
	def test_requirements_run_once_per_loaded_library(cls):
		ownership = cls._ownership()

		try:
			with tempfile.TemporaryDirectory() as home:
				source = cls._library(home, 'deps_lib')
				requirements = os.path.join(source, 'requirements.txt')

				with open(requirements, 'w') as stream:
					stream.write('test-package>=1\n')

				with patch.dict(os.environ, {'ALMASI_PATH': home}):
					with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as runner:
						log = StringIO()

						with redirect_stderr(log):
							with patch.dict(sys.modules):
								library = almasi.services.Libraries.imp('deps_lib')
								assert almasi.services.Libraries.imp('deps_lib') is library

							with patch.dict(sys.modules):
								almasi.services.Libraries.imp('deps_lib')

						assert runner.call_count == 2
						assert runner.call_args.args[0] == [
							sys.executable, '-m', 'pip', 'install', '-r', requirements
						]
						assert runner.call_args.kwargs['cwd'] == source
						assert log.getvalue().count('✔ almasi.deps_lib: Installing dependencies') == 2, repr(log.getvalue())
		finally:
			almasi.Imports.__lib__, almasi.Tester.__lib__, almasi.Undefined.__lib__ = ownership
			almasi.__dict__.pop('deps_lib', None)

	# Do not publish a library whose dependencies could not be prepared.
	# ----------------------------------------------------------------------
	@classmethod
	def test_failed_requirements_prevent_import(cls):
		with tempfile.TemporaryDirectory() as home:
			source = cls._library(home, 'missing_deps')

			with open(os.path.join(source, 'requirements.txt'), 'w') as stream:
				stream.write('unavailable-package\n')

			failure = subprocess.CalledProcessError(1, ['pip'], stderr='dependency unavailable')
			log     = StringIO()

			with redirect_stderr(log):
				with patch.dict(os.environ, {'ALMASI_PATH': home}):
					with patch('subprocess.run', side_effect=failure):
						with patch.dict(sys.modules):
							with TestCase().assertRaises(subprocess.CalledProcessError) as raised:
								almasi.services.Libraries.imp('missing_deps')

							assert raised.exception is failure

							assert 'almasi.missing_deps' not in sys.modules

			assert '❌ almasi.missing_deps: Installing dependencies' in log.getvalue()

	# Reject invalid names before constructing a Git command or a module.
	# ----------------------------------------------------------------------
	@classmethod
	def test_invalid_names_do_not_resolve(cls):
		with TestCase().assertRaises(ValueError):
			almasi.services.Libraries.imp('../outside')

		with TestCase().assertRaises(ValueError):
			almasi.services.Libraries.clone('NotSnakeCase')

	# Failed source execution leaves no falsely published library module.
	# ----------------------------------------------------------------------
	@classmethod
	def test_failed_import_cleans_publication(cls):
		with tempfile.TemporaryDirectory() as home:
			cls._library(home, 'broken_lib', '''raise RuntimeError('broken source')
''')

			with patch.dict(os.environ, {'ALMASI_PATH': home}):
				with patch.dict(sys.modules):
					with TestCase().assertRaisesRegex(RuntimeError, 'broken source'):
						almasi.services.Libraries.imp('broken_lib')

					assert 'almasi.broken_lib' not in sys.modules


if __name__ == '__main__':
	TestLibraries.run()
