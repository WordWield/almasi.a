# ==============================================================================
# TEST GIT
# ==============================================================================
# PURPOSE:
# Verify local Git operations and remote GitHub commands without network writes.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: CLI command and failure contract assertions.
# Delegates: Actual GitHub communication to the Git service.
# ==============================================================================

import asyncio
import os
import subprocess
import sys
import tempfile

from unittest.mock import AsyncMock, patch

from almasi import a


class TestGit(a.Tester):

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Run temporary-repository commands without the user's Git hooks.
	# ----------------------------------------------------------------------
	@classmethod
	def _git(cls, directory, *arguments):
		result = subprocess.run(
			['git', '-c', 'core.hooksPath=/dev/null', '-C', directory, *arguments],
			capture_output = True,
			text           = True,
			check          = True
		)

		return result.stdout.strip()

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Resolve the shared Git service without explicit initialization.
	# ----------------------------------------------------------------------
	@classmethod
	def test_service_identity(cls):
		git = a.services.Git

		assert isinstance(git, a.Singleton)
		assert git is a.services.Git
		assert git is type(git)()

	# Exercise clone, fast-forward pull and checkout recognition with real Git.
	# ----------------------------------------------------------------------
	@classmethod
	def test_local_checkout(cls):
		git = a.services.Git

		with tempfile.TemporaryDirectory(prefix='almasi_git_test_') as directory:
			origin   = os.path.join(directory, 'origin')
			checkout = os.path.join(directory, 'checkout')

			subprocess.run(['git', 'init', '--quiet', origin], check=True)
			filename = os.path.join(origin, 'example.txt')

			with open(filename, 'w') as stream:
				stream.write('first')

			subprocess.run(['git', '-C', origin, 'add', '.'], check=True)
			commit = [
				'git', '-C', origin,
				'-c', 'user.name=Almasi Test',
				'-c', 'user.email=test@example.test',
				'-c', 'commit.gpgSign=false',
				'-c', f'core.hooksPath={os.devnull}',
				'commit', '--quiet', '-m'
			]
			subprocess.run([*commit, 'Initial'], check=True)

			assert git.is_cloned(origin)
			assert not git.is_cloned(checkout)
			with patch.object(git, '_to_url', return_value=origin):
				assert git.clone('owner', 'repo', checkout) == checkout
			assert git.is_cloned(checkout)

			with open(filename, 'w') as stream:
				stream.write('second')

			subprocess.run(['git', '-C', origin, 'add', '.'], check=True)
			subprocess.run([*commit, 'Update'], check=True)

			assert asyncio.run(git.pull(checkout)) == subprocess.check_output(['git', '-C', origin, 'rev-parse', 'HEAD'], text=True).strip()

			with open(os.path.join(checkout, 'example.txt')) as stream:
				assert stream.read() == 'second'

	# Prevent checkout and push hooks from interfering with automated commands.
	# ----------------------------------------------------------------------
	@classmethod
	def test_ignore_hooks(cls):
		git = a.services.Git

		with tempfile.TemporaryDirectory(prefix='almasi_git_hooks_') as directory:
			origin   = os.path.join(directory, 'origin')
			checkout = os.path.join(directory, 'checkout')
			hooks    = os.path.join(directory, 'hooks')
			os.makedirs(hooks)

			for name in ('post-checkout', 'pre-push'):
				path = os.path.join(hooks, name)

				with open(path, 'w') as stream:
					stream.write('#!/bin/sh\nexit 91\n')

				os.chmod(path, 0o755)

			subprocess.run(['git', 'init', '--quiet', origin], check=True)
			subprocess.run([
				'git', '-C', origin,
				'-c', 'user.name=Almasi Test',
				'-c', 'user.email=test@example.test',
				'-c', 'commit.gpgSign=false',
				'-c', f'core.hooksPath={os.devnull}',
				'commit', '--quiet', '--allow-empty', '-m', 'Fixture'
			], check=True)

			environment = {
				'GIT_CONFIG_COUNT'   : '1',
				'GIT_CONFIG_KEY_0'   : 'core.hooksPath',
				'GIT_CONFIG_VALUE_0' : hooks
			}

			with patch.dict(os.environ, environment), patch.object(git, '_to_url', return_value=origin):
				git.clone('owner', 'repo', checkout)
				assert git.is_cloned(checkout)

				arguments = ['git', '-C', checkout, 'push', 'origin', 'HEAD:refs/heads/copied']

				blocked = subprocess.run(arguments, capture_output=True, text=True)
				assert blocked.returncode != 0

				git._run(arguments)

				assert os.environ['GIT_CONFIG_COUNT'] == '1'
				assert os.environ['GIT_CONFIG_VALUE_0'] == hooks

	# Apply the same subprocess environment to GitHub CLI and its Git children.
	# ----------------------------------------------------------------------
	@classmethod
	def test_github_child_environment(cls):
		git = a.services.Git

		with patch.dict(os.environ, {'GIT_CONFIG_COUNT': '0'}):
			with patch('subprocess.run') as run:
				git._gh(['repo', 'create', 'owner/repo', '--private'])

				assert run.call_args.args[0] == ['gh', 'repo', 'create', 'owner/repo', '--private']

				environment = run.call_args.kwargs['env']
				assert environment['GIT_CONFIG_COUNT'] == '1'
				assert environment['GIT_CONFIG_KEY_0'] == 'core.hooksPath'
				assert environment['GIT_CONFIG_VALUE_0'] == os.devnull
				assert environment['GIT_TERMINAL_PROMPT'] == '0'
				assert environment['GH_PROMPT_DISABLED'] == '1'

	# Apply an explicit token only to a child environment, never global state.
	# ----------------------------------------------------------------------
	@classmethod
	def test_token_environment(cls):
		git = a.services.Git

		with patch.dict(os.environ, {'GH_TOKEN': 'ordinary-test-token', 'GIT_CONFIG_COUNT': '0'}):
			with patch('subprocess.run') as run:
				git.delete_remote('owner', 'repo', token='scoped-test-token')

				environment = run.call_args.kwargs['env']
				assert environment['GH_TOKEN'] == 'scoped-test-token'
				assert environment['GIT_CONFIG_COUNT'] == '3'
				assert environment['GIT_CONFIG_KEY_1'] == 'credential.https://github.com.helper'
				assert environment['GIT_CONFIG_VALUE_1'] == ''
				assert environment['GIT_CONFIG_KEY_2'] == 'credential.https://github.com.helper'
				assert environment['GIT_CONFIG_VALUE_2'] == '!gh auth git-credential'
				assert 'scoped-test-token' not in run.call_args.args[0]
				assert os.environ['GH_TOKEN'] == 'ordinary-test-token'
				assert os.environ['GIT_CONFIG_COUNT'] == '0'

				git.delete_remote('owner', 'repo')
				assert run.call_args.kwargs['env']['GH_TOKEN'] == 'ordinary-test-token'
				assert run.call_args.kwargs['env']['GIT_CONFIG_COUNT'] == '1'

				run.reset_mock()

				for token in ('', 'invalid token'):
					try:
						git.delete_remote('owner', 'repo', token=token)
					except ValueError:
						run.assert_not_called()
					else:
						assert False, 'Invalid token was accepted'

	# Keep source authentication separate from destination administration.
	# ----------------------------------------------------------------------
	@classmethod
	def test_create_destination_token(cls):
		git = a.services.Git

		with patch.object(git, 'clone') as clone, patch.object(git, '_gh') as gh, patch.object(git, '_run') as run:
			git.create_remote('owner', 'new', from_owner='base', from_name='old', token='scoped-test-token')

			owner, name, path = clone.call_args.args
			clone.assert_called_once_with('base', 'old', path)
			gh.assert_called_once_with(['repo', 'create', 'owner/new', '--private'], token='scoped-test-token')
			run.assert_called_once_with(['git', '-C', path, 'push', '--quiet', '--', 'https://github.com/owner/new.git', 'HEAD'], token='scoped-test-token')

	# Verify the token reaches each authenticated operation.
	# ----------------------------------------------------------------------
	@classmethod
	def test_remote_tokens(cls):
		git   = a.services.Git
		token = 'scoped-test-token'

		with patch.object(git, '_gh') as gh:
			gh.return_value = subprocess.CompletedProcess([], 0, 'HTTP/2 200 OK', '')
			git.list_remotes('owner', token=token)
			assert gh.call_args.kwargs['token'] == token

			git.exists_remote('owner', 'repo', token=token)
			assert gh.call_args.kwargs['token'] == token

			git.create_remote('owner', 'repo', token=token)
			assert gh.call_args.kwargs['token'] == token

			git.rename_remote('owner', 'repo', 'new', token=token)
			assert gh.call_args.kwargs['token'] == token

		with patch('subprocess.run') as run:
			git.clone('owner', 'repo', '/checkout', token=token)
			assert run.call_args.kwargs['env']['GH_TOKEN'] == token

	# Supply a credential only to pull's network command, in either mode.
	# ----------------------------------------------------------------------
	@classmethod
	def test_pull_token(cls):
		git   = a.services.Git
		token = 'scoped-test-token'

		with tempfile.TemporaryDirectory() as directory:
			origin   = os.path.join(directory, 'origin')
			checkout = os.path.join(directory, 'checkout')

			subprocess.run(['git', 'init', '-q', '-b', 'master', origin], check=True)
			cls._git(origin, 'config', 'user.name', 'Test')
			cls._git(origin, 'config', 'user.email', 'test@example.org')
			cls._git(origin, 'commit', '-qm', 'Initial', '--allow-empty')
			subprocess.run(['git', 'clone', '-q', origin, checkout], check=True)

			with patch.object(git, '_run_async', new_callable=AsyncMock) as run:
				for exact in (False, True):
					asyncio.run(git.pull(checkout, exact=exact, token=token))
					assert run.call_args.kwargs['token'] == token

	# Retain native exceptions while exposing captured diagnostics in tracebacks.
	# ----------------------------------------------------------------------
	@classmethod
	def test_failure_diagnostics(cls):
		git = a.services.Git

		try:
			git._run([sys.executable, '-c', 'import sys; print("rejected", file=sys.stderr); sys.exit(1)'])
		except subprocess.CalledProcessError as error:
			assert error.returncode == 1
			assert 'rejected' in error.__notes__
		else:
			assert False, 'The command must fail'

	# Read all repository names from the authenticated paginated GitHub query.
	# ----------------------------------------------------------------------
	@classmethod
	def test_list_remotes(cls):
		git = a.services.Git

		with patch.object(git, '_gh') as gh:
			gh.return_value = subprocess.CompletedProcess([], 0, 'one\ntwo\n', '')
			assert git.list_remotes('owner') == ['one', 'two']

			arguments = gh.call_args.args[0]
			assert arguments[:5] == ['api', 'graphql', '--hostname', git._HOST, '--paginate']
			assert 'owner=owner' in arguments
			assert 'pageInfo { hasNextPage endCursor }' in arguments[6]

			gh.reset_mock()

			try:
				git.list_remotes('owner/repo')
			except ValueError:
				gh.assert_not_called()
			else:
				assert False, 'Only an owner is accepted'

			gh.side_effect = subprocess.CalledProcessError(1, ['gh'])

			try:
				git.list_remotes('owner')
			except subprocess.CalledProcessError:
				assert gh.called
			else:
				assert False, 'Discovery errors must propagate'

	# Distinguish a missing repository from authentication and network errors.
	# ----------------------------------------------------------------------
	@classmethod
	def test_exists_remote(cls):
		git = a.services.Git

		with patch.object(git, '_gh') as gh:
			gh.return_value = subprocess.CompletedProcess([], 0, 'HTTP/2 200 OK', '')
			assert git.exists_remote('owner', 'repo') is True

			gh.return_value = subprocess.CompletedProcess([], 1, 'HTTP/2 404 Not Found', 'gh: Not Found')
			assert git.exists_remote('owner', 'repo') is False

			gh.return_value = subprocess.CompletedProcess([], 1, 'HTTP/2 403 Forbidden', 'gh: Forbidden')

			try:
				git.exists_remote('owner', 'repo')
			except RuntimeError as error:
				assert 'Forbidden' in str(error)
			else:
				assert False, 'A permission error must not report a missing repository'

			gh.return_value = subprocess.CompletedProcess([], 1, '', 'network unavailable')

			try:
				git.exists_remote('owner', 'repo')
			except RuntimeError as error:
				assert 'network unavailable' in str(error)
			else:
				assert False, 'A network error must not report a missing repository'

	# Create with the requested visibility and explicit owner.
	# ----------------------------------------------------------------------
	@classmethod
	def test_create_empty(cls):
		git = a.services.Git

		with patch.object(git, '_gh') as gh:
			assert git.create_remote('owner', 'repo') is None
			gh.assert_called_once_with(['repo', 'create', 'owner/repo', '--private'], token=None)

		with patch.object(git, '_gh') as gh:
			git.create_remote('owner', 'repo', private=False)
			gh.assert_called_once_with(['repo', 'create', 'owner/repo', '--public'], token=None)

	# Seed from an ordinary repository, without requiring GitHub template flags.
	# ----------------------------------------------------------------------
	@classmethod
	def test_create_from_repository(cls):
		git = a.services.Git

		with patch.object(git, 'clone') as clone, patch.object(git, '_gh') as gh, patch.object(git, '_run') as run:
			assert git.create_remote('owner', 'new', from_owner='base', from_name='old') is None

			owner, name, path = clone.call_args.args
			assert (owner, name) == ('base', 'old')
			gh.assert_called_once_with(['repo', 'create', 'owner/new', '--private'], token=None)
			run.assert_called_once_with(['git', '-C', path, 'push', '--quiet', '--', 'https://github.com/owner/new.git', 'HEAD'], token=None)

	# Delete only the explicit remote and propagate provider failures.
	# ----------------------------------------------------------------------
	@classmethod
	def test_delete_remote(cls):
		git = a.services.Git

		with patch.object(git, '_gh') as gh:
			assert git.delete_remote('owner', 'repo') is None
			gh.assert_called_once_with(['api', '--hostname', git._HOST, '--method', 'DELETE', 'repos/owner/repo'], token=None)
			gh.reset_mock()

			for owner, name in (('', 'repo'), ('owner', '..'), ('owner', 'repo/extra'), ('https://github.com/owner', 'repo')):
				try:
					git.delete_remote(owner, name)
				except ValueError:
					gh.assert_not_called()
				else:
					assert False, 'Invalid repository was accepted'

			gh.side_effect = subprocess.CalledProcessError(1, ['gh'])

			try:
				git.delete_remote('owner', 'repo')
			except subprocess.CalledProcessError:
				gh.assert_called_once()
			else:
				assert False, 'Deletion failure must propagate'

	# Rename within the current owner without creating or deleting a repository.
	# ----------------------------------------------------------------------
	@classmethod
	def test_rename_remote(cls):
		git = a.services.Git

		with patch.object(git, '_gh') as gh:
			assert git.rename_remote('owner', 'old', 'new.name') is None
			gh.assert_called_once_with(['api', '--hostname', git._HOST, '--method', 'PATCH', 'repos/owner/old', '-f', 'name=new.name'], token=None)
			gh.reset_mock()

			for owner, name, new_name in (('', 'old', 'new'), ('owner', 'old', 'other/new'), ('owner', 'old', '..'), ('owner', 'old', ''), ('owner', 'old', None)):
				try:
					git.rename_remote(owner, name, new_name)
				except ValueError:
					gh.assert_not_called()
				else:
					assert False, 'Invalid rename was accepted'

			gh.side_effect = subprocess.CalledProcessError(1, ['gh'])

			try:
				git.rename_remote('owner', 'old', 'new')
			except subprocess.CalledProcessError:
				gh.assert_called_once()
			else:
				assert False, 'Rename failure must propagate'

	# Update the tracked remote, not an assumed origin or the working tree.
	# ----------------------------------------------------------------------
	@classmethod
	def test_set_remote(cls):
		git = a.services.Git

		with tempfile.TemporaryDirectory(prefix='almasi_git_url_') as directory:
			origin   = os.path.join(directory, 'origin')
			checkout = os.path.join(directory, 'checkout')

			subprocess.run(['git', 'init', '-q', '-b', 'master', origin], check=True)
			cls._git(origin, 'config', 'user.name', 'Test')
			cls._git(origin, 'config', 'user.email', 'test@example.org')
			cls._git(origin, 'commit', '-qm', 'Initial', '--allow-empty')
			subprocess.run(['git', 'clone', '-q', origin, checkout], check=True)

			cls._git(checkout, 'remote', 'rename', 'origin', 'upstream')
			cls._git(checkout, 'remote', 'add', 'origin', 'https://github.com/owner/unrelated.git')
			cls._git(checkout, 'remote', 'set-url', '--push', 'upstream', 'https://github.com/owner/publish.git')

			commit = cls._git(checkout, 'rev-parse', 'HEAD')
			branch = cls._git(checkout, 'rev-parse', '--abbrev-ref', '@{upstream}')
			for url in ('https://github.com/owner/old.git', 'https://github.com/owner/old', 'git@github.com:owner/old.git', 'ssh://git@github.com/owner/old.git'):
				cls._git(checkout, 'remote', 'set-url', 'upstream', url)
				assert git.get_remote(checkout) == ('owner', 'old')

			assert git.set_remote(checkout, 'owner', 'renamed') is None
			assert git.get_remote(checkout) == ('owner', 'renamed')
			assert cls._git(checkout, 'remote', 'get-url', 'upstream') == 'https://github.com/owner/renamed.git'
			assert cls._git(checkout, 'remote', 'get-url', 'origin') == 'https://github.com/owner/unrelated.git'
			assert cls._git(checkout, 'remote', 'get-url', '--push', 'upstream') == 'https://github.com/owner/publish.git'
			assert cls._git(checkout, 'rev-parse', 'HEAD') == commit
			assert cls._git(checkout, 'rev-parse', '--abbrev-ref', '@{upstream}') == branch

			for url in (origin, 'https://example.org/owner/repo.git', 'https://github.com/owner/repo/extra'):
				cls._git(checkout, 'remote', 'set-url', 'upstream', url)

				try:
					git.get_remote(checkout)
				except ValueError:
					assert cls._git(checkout, 'remote', 'get-url', 'upstream') == url
				else:
					assert False, 'A non-GitHub upstream was accepted'

			git.set_remote(checkout, 'owner', 'renamed')

			try:
				git.set_remote(directory, 'owner', 'renamed')
			except ValueError:
				assert git.get_remote(checkout) == ('owner', 'renamed')
			else:
				assert False, 'An exact checkout root is required'

	# Reject incomplete source identities before creating a repository.
	# ----------------------------------------------------------------------
	@classmethod
	def test_create_requires_source_coordinates(cls):
		git = a.services.Git

		with patch.object(git, '_gh') as gh, patch.object(git, 'clone') as clone:
			for owner, name in (('base', None), (None, 'old')):
				try:
					git.create_remote('owner', 'new', from_owner=owner, from_name=name)
				except ValueError:
					gh.assert_not_called()
					clone.assert_not_called()
				else:
					assert False, 'Both source coordinates are required'

	# Derive the clone address internally from the two remote coordinates.
	# ----------------------------------------------------------------------
	@classmethod
	def test_clone_coordinates(cls):
		git = a.services.Git

		with patch.object(git, '_run') as run:
			assert git.clone('owner', 'repo.name', '/checkout', timeout=5) == '/checkout'
			run.assert_called_once_with(['git', 'clone', '--quiet', '--', 'https://github.com/owner/repo.name.git', '/checkout'], timeout=5, token=None)

	# Reject ambiguous names before invoking the CLI.
	# ----------------------------------------------------------------------
	@classmethod
	def test_invalid_repository(cls):
		git = a.services.Git

		with patch.object(git, '_gh') as gh:
			try:
				git.exists_remote('', 'repo')
			except ValueError:
				assert not gh.called
			else:
				assert False, 'An explicit owner is required'

	# Pull forward and backward without keeping any deployment history.
	# ----------------------------------------------------------------------
	@classmethod
	def test_pull_matches_remote_head(cls):
		with tempfile.TemporaryDirectory() as folder:
			remote = os.path.join(folder, 'remote.git')
			writer = os.path.join(folder, 'writer')
			local  = os.path.join(folder, 'local')
			os.mkdir(writer)
			cls._git(writer, 'init', '-q', '-b', 'master')
			cls._git(writer, 'config', 'user.name', 'Test')
			cls._git(writer, 'config', 'user.email', 'test@example.org')
			file = os.path.join(writer, 'app.py')

			with open(file, 'w', encoding='utf-8') as stream:
				stream.write('version = 1\n')

			cls._git(writer, 'add', '.')
			cls._git(writer, 'commit', '-qm', 'A')
			first = cls._git(writer, 'rev-parse', 'HEAD')
			subprocess.run(['git', 'init', '-q', '--bare', remote], check=True)
			cls._git(writer, 'remote', 'add', 'origin', remote)
			cls._git(writer, 'push', '-q', '-u', 'origin', 'master')
			subprocess.run(['git', 'clone', '-q', '-b', 'master', remote, local], check=True)

			service = a.services.Git

			with open(file, 'w', encoding='utf-8') as stream:
				stream.write('version = 2\n')

			cls._git(writer, 'commit', '-qam', 'B')
			b = cls._git(writer, 'rev-parse', 'HEAD')
			cls._git(writer, 'push', '-q', 'origin', 'master')
			assert asyncio.run(service.pull(local, exact=True)) == b
			assert cls._git(local, 'rev-parse', 'HEAD') == b

			cls._git(writer, 'reset', '--hard', first)
			cls._git(writer, 'push', '-q', '--force', 'origin', 'master')
			assert asyncio.run(service.pull(local, exact=True)) == first
			assert cls._git(local, 'rev-parse', 'HEAD') == first

			with open(os.path.join(local, 'app.py'), 'a', encoding='utf-8') as stream:
				stream.write('# Uncommitted\n')

			try:
				asyncio.run(service.pull(local, exact=True))
			except RuntimeError as error:
				assert 'Uncommitted' in str(error)
			else:
				raise AssertionError('Dirty tracked files were overwritten')
