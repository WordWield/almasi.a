# ==============================================================================
# CHECKOUT SERVICE
# ==============================================================================
# PURPOSE:
# Synchronize a dedicated working tree with the current upstream commit.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Git repository selection and synchronization of tracked files.
# Delegates: Source loading and change observation to Almasi; O remains intact.
# ==============================================================================

import asyncio
import os
import subprocess

from almasi import a


class Checkout(a.Singleton):

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Inspect the configured repository without invoking a shell.
	# ----------------------------------------------------------------------
	def _git(self, *arguments):
		process = subprocess.run(
			['git', '-C', self.repository, *arguments],
			capture_output = True,
			text           = True,
			check          = False
		)

		if process.returncode == 0:
			result = process.stdout.strip()
		else:
			raise RuntimeError(process.stderr.strip())

		return result

	# Fetch updates from the configured tracking remote.
	# ----------------------------------------------------------------------
	async def _fetch(self):
		process = await asyncio.create_subprocess_exec(
			'git', '-C', self.repository, 'fetch', '--quiet', '--no-tags', self.remote,
			stdout = asyncio.subprocess.PIPE,
			stderr = asyncio.subprocess.PIPE
		)

		try:
			stdout, stderr = await process.communicate()
		except asyncio.CancelledError:
			process.kill()
			await process.wait()
			raise

		if process.returncode != 0:
			raise RuntimeError(stderr.decode('utf-8', errors='replace').strip())

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Bind a dedicated working tree to its existing Git upstream.
	# ----------------------------------------------------------------------
	def initialize(self, directory):
		'''Configure an existing Git checkout with an upstream tracking branch.'''
		path = os.path.realpath(directory)

		if os.path.isdir(path):
			process = subprocess.run(
				['git', '-C', path, 'rev-parse', '--show-toplevel'],
				capture_output = True,
				text           = True,
				check          = True
			)
			self.repository = os.path.realpath(process.stdout.strip())
			self.upstream   = self._git('rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}')
			self.remote     = self.upstream.split('/', 1)[0]
			self.lock       = asyncio.Lock()
		else:
			raise ValueError('Expected an existing Git working directory')

	# Return the repository URL from the configured Git tracking remote.
	# ----------------------------------------------------------------------
	def get_repo(self):
		'''Return the URL of the remote tracked by this checkout.'''
		return self._git('remote', 'get-url', self.remote)

	# Make local tracked code match the latest remote HEAD, including rewinds.
	# ----------------------------------------------------------------------
	async def pull(self):
		'''Fetch upstream and reset tracked code to its HEAD; never touch O storage.'''
		async with self.lock:
			if not self._git('status', '--porcelain', '--untracked-files=no'):
				await self._fetch()
				commit = self._git('rev-parse', '--verify', self.upstream + '^{commit}')
				current = self._git('rev-parse', 'HEAD')

				if current != commit:
					self._git('reset', '--hard', '--quiet', commit)
			else:
				raise RuntimeError('Uncommitted tracked files prevent Git synchronization')

		return commit
