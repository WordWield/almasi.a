# ==============================================================================
# TEST GIT
# ==============================================================================
# PURPOSE:
# Verify remote Git operations without creating real GitHub repositories.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: CLI command and failure contract assertions.
# Delegates: Actual GitHub communication to the Git service.
# ==============================================================================

import subprocess

from unittest.mock import patch

from almasi import a


class TestGit(a.Tester):

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

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
