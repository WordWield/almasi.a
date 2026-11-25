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

from unittest.mock import patch

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

			assert git.is_repository(origin)
			assert not git.is_repository(checkout)
			assert git.clone(origin, checkout) == checkout
			assert git.is_repository(checkout)

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

			with patch.dict(os.environ, environment):
				git.clone(origin, checkout)
				assert git.is_repository(checkout)

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
	def test_list_repositories(cls):
		git = a.services.Git

		with patch.object(git, '_gh') as gh:
			gh.return_value = subprocess.CompletedProcess([], 0, 'one\ntwo\n', '')
			assert git.list_repositories('owner') == ['one', 'two']

			arguments = gh.call_args.args[0]
			assert arguments[:5] == ['api', 'graphql', '--hostname', git._HOST, '--paginate']
			assert 'owner=owner' in arguments
			assert 'pageInfo { hasNextPage endCursor }' in arguments[6]

			gh.reset_mock()

			try:
				git.list_repositories('owner/repo')
			except ValueError:
				gh.assert_not_called()
			else:
				assert False, 'Only an owner is accepted'

			gh.side_effect = subprocess.CalledProcessError(1, ['gh'])

			try:
				git.list_repositories('owner')
			except subprocess.CalledProcessError:
				assert gh.called
			else:
				assert False, 'Discovery errors must propagate'

	# Distinguish a missing repository from authentication and network errors.
	# ----------------------------------------------------------------------
	@classmethod
	def test_exists(cls):
		git = a.services.Git

		with patch.object(git, '_gh') as gh:
			gh.return_value = subprocess.CompletedProcess([], 0, 'HTTP/2 200 OK', '')
			assert git.exists('owner/repo') is True

			gh.return_value = subprocess.CompletedProcess([], 1, 'HTTP/2 404 Not Found', 'gh: Not Found')
			assert git.exists('owner/repo') is False

			gh.return_value = subprocess.CompletedProcess([], 1, 'HTTP/2 403 Forbidden', 'gh: Forbidden')

			try:
				git.exists('owner/repo')
			except RuntimeError as error:
				assert 'Forbidden' in str(error)
			else:
				assert False, 'A permission error must not report a missing repository'

			gh.return_value = subprocess.CompletedProcess([], 1, '', 'network unavailable')

			try:
				git.exists('owner/repo')
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
			assert git.create('owner/repo') == 'https://github.com/owner/repo.git'
			gh.assert_called_once_with(['repo', 'create', 'owner/repo', '--private'])

		with patch.object(git, '_gh') as gh:
			git.create('owner/repo', private=False)
			gh.assert_called_once_with(['repo', 'create', 'owner/repo', '--public'])

	# Seed from an ordinary repository, without requiring GitHub template flags.
	# ----------------------------------------------------------------------
	@classmethod
	def test_create_from_repository(cls):
		git = a.services.Git

		with patch.object(git, 'clone') as clone, patch.object(git, '_gh') as gh:
			assert git.create('owner/new', from_repository='base/old') == 'https://github.com/owner/new.git'

			url, directory = clone.call_args.args
			assert url == 'https://github.com/base/old.git'
			gh.assert_called_once_with([
				'repo', 'create', 'owner/new', '--private',
				'--source', directory, '--remote', 'destination', '--push'
			])

	# Reject ambiguous names before invoking the CLI.
	# ----------------------------------------------------------------------
	@classmethod
	def test_invalid_repository(cls):
		git = a.services.Git

		with patch.object(git, '_gh') as gh:
			try:
				git.exists('repo')
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
			assert service.get_repository_url(local) == remote

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
