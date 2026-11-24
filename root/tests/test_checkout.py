# ==============================================================================
# TEST CHECKOUT
# ==============================================================================
# PURPOSE:
# Verify synchronization to a remote branch after forward and backward moves.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Temporary repository setup and Git behavior assertions.
# Delegates: Synchronization to the Checkout service.
# ==============================================================================

import asyncio
import os
import subprocess
import tempfile

from almasi import a


class TestCheckout(a.Tester):

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

			service = a.services.Checkout
			service.initialize(local)
			assert service.get_repo() == remote

			with open(file, 'w', encoding='utf-8') as stream:
				stream.write('version = 2\n')

			cls._git(writer, 'commit', '-qam', 'B')
			b = cls._git(writer, 'rev-parse', 'HEAD')
			cls._git(writer, 'push', '-q', 'origin', 'master')
			assert asyncio.run(service.pull()) == b
			assert cls._git(local, 'rev-parse', 'HEAD') == b

			cls._git(writer, 'reset', '--hard', first)
			cls._git(writer, 'push', '-q', '--force', 'origin', 'master')
			assert asyncio.run(service.pull()) == first
			assert cls._git(local, 'rev-parse', 'HEAD') == first

			with open(os.path.join(local, 'app.py'), 'a', encoding='utf-8') as stream:
				stream.write('# Uncommitted\n')

			try:
				asyncio.run(service.pull())
			except RuntimeError as error:
				assert 'Uncommitted' in str(error)
			else:
				raise AssertionError('Dirty tracked files were overwritten')
