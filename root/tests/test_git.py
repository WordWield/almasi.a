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

import os
import subprocess
import sys
import tempfile

from unittest.mock import patch

from almasi import a


class TestGit(a.Tester):

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

			git.pull(checkout)

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
			assert git.create('owner/new', from_repo='base/old') == 'https://github.com/owner/new.git'

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
