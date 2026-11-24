# ==============================================================================
# TEST GIT
# ==============================================================================
# PURPOSE:
# Exercise Git acquisition and fast-forward updates on real local repositories.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Isolated repository fixtures and public API assertions.
# Delegates: Checkout operations to Git and fixture creation to the Git CLI.
# ==============================================================================

import os
import subprocess
import tempfile
from unittest import TestCase

import almasi


class TestGit(almasi.Tester):

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Create fixture commits without user signing or hooks.
	# ----------------------------------------------------------------------
	@staticmethod
	def _commit(directory, content):
		with open(os.path.join(directory, 'data.txt'), 'w') as file:
			file.write(content)

		subprocess.run(
			['git', '-C', directory, 'add', 'data.txt'],
			check=True, capture_output=True
		)
		subprocess.run(
			[
				'git', '-C', directory,
				'-c', 'user.name=Almasi Test',
				'-c', 'user.email=almasi@example.test',
				'-c', 'commit.gpgSign=false',
				'-c', f'core.hooksPath={os.devnull}',
				'commit', '-qm', content
			],
			check=True, capture_output=True
		)

	# Create a repository with a committed file.
	# ----------------------------------------------------------------------
	@classmethod
	def _origin(cls, directory):
		subprocess.run(['git', 'init', '-q', directory], check=True, capture_output=True)
		cls._commit(directory, 'initial')

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Acquire a working checkout and update it from its configured origin.
	# ----------------------------------------------------------------------
	@classmethod
	def test_clone_and_pull(cls):
		git = almasi.services.Git
		assert git is almasi.services.Git
		assert isinstance(git, almasi.Singleton)

		with tempfile.TemporaryDirectory() as home:
			origin   = os.path.join(home, 'origin')
			checkout = os.path.join(home, 'nested', 'checkout')
			cls._origin(origin)

			assert not git.is_repository(checkout)
			assert git.clone(origin, checkout) == checkout
			assert git.is_repository(checkout)

			with open(os.path.join(checkout, 'data.txt')) as file:
				assert file.read() == 'initial'

			cls._commit(origin, 'updated')
			git.pull(checkout, timeout=15)

			with open(os.path.join(checkout, 'data.txt')) as file:
				assert file.read() == 'updated'

	# Reject nested directories and invalid markers; recognize linked worktrees.
	# ----------------------------------------------------------------------
	@classmethod
	def test_repository_identity(cls):
		git = almasi.services.Git

		with tempfile.TemporaryDirectory() as home:
			origin   = os.path.join(home, 'origin')
			nested   = os.path.join(origin, 'nested')
			worktree = os.path.join(home, 'worktree')
			cls._origin(origin)
			os.mkdir(nested)

			assert not git.is_repository(home)
			assert not git.is_repository(nested)

			with TestCase().assertRaises(subprocess.CalledProcessError):
				git.pull(nested)

			os.mkdir(os.path.join(nested, '.git'))
			assert not git.is_repository(nested)

			subprocess.run(
				['git', '-C', origin, 'worktree', 'add', '-qb', 'linked', worktree],
				check=True, capture_output=True
			)
			assert git.is_repository(worktree)

	# Preserve a divergent local commit and expose the failed update to callers.
	# ----------------------------------------------------------------------
	@classmethod
	def test_divergence(cls):
		git = almasi.services.Git

		with tempfile.TemporaryDirectory() as home:
			origin   = os.path.join(home, 'origin')
			checkout = os.path.join(home, 'checkout')
			cls._origin(origin)
			git.clone(origin, checkout)

			cls._commit(checkout, 'local')
			cls._commit(origin,   'remote')

			with TestCase().assertRaises(subprocess.CalledProcessError):
				git.pull(checkout)

			with open(os.path.join(checkout, 'data.txt')) as file:
				assert file.read() == 'local'

	# Expose clone failures without reporting a usable checkout.
	# ----------------------------------------------------------------------
	@classmethod
	def test_failed_clone(cls):
		with tempfile.TemporaryDirectory() as home:
			git      = almasi.services.Git
			checkout = os.path.join(home, 'checkout')

			with TestCase().assertRaises(subprocess.CalledProcessError):
				git.clone(os.path.join(home, 'missing'), checkout)

			assert not git.is_repository(checkout)
