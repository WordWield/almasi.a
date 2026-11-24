# ==============================================================================
# TEST PROGRESS
# ==============================================================================
# PURPOSE:
# Verify actual terminal output and exception propagation for progress contexts.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Output and lifecycle assertions.
# Delegates: Terminal rendering to Progress and the native pseudo-terminal.
# ==============================================================================

import asyncio
import os
from contextlib import redirect_stderr
from io         import StringIO

import almasi


class TestProgress(almasi.Tester):

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Exercise the native asynchronous context protocol.
	# ----------------------------------------------------------------------
	@staticmethod
	async def _run_async(stream):
		async with almasi.Progress('Waiting', stream=stream) as progress:
			progress.update('Ready')

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Redirected output contains only the final text and subsequent corrections.
	# ----------------------------------------------------------------------
	@classmethod
	def test_redirected_output(cls):
		stream = StringIO()

		with almasi.Progress('Starting', stream=stream) as progress:
			progress.update('Working')
			progress.update('Done')
			assert stream.getvalue() == ''

		assert stream.getvalue() == '✔ Done\n'
		progress.update('Verified')
		assert stream.getvalue() == '✔ Done\n✔ Verified\n'

	# Failure leaves the original exception intact and retains its status.
	# ----------------------------------------------------------------------
	@classmethod
	def test_failure(cls):
		stream  = StringIO()
		failure = ValueError('original')

		try:
			with almasi.Progress('Starting', stream=stream) as progress:
				progress.update('Failed operation')
				raise failure
		except ValueError as error:
			assert error is failure
		else:
			assert False, 'Progress swallowed the exception'

		assert stream.getvalue() == '❌ Failed operation\n'
		progress.update('Explained')
		assert stream.getvalue().endswith('❌ Explained\n')

	# Update the completed terminal row without adding another visible row.
	# ----------------------------------------------------------------------
	@classmethod
	def test_terminal_replacement(cls):
		master, slave = os.openpty()

		try:
			with os.fdopen(slave, 'w', encoding='utf-8') as stream:
				with almasi.Progress('Starting', stream=stream) as progress:
					progress.update('Completed')

				progress.update('Verified')
				os.set_blocking(master, False)
				output = os.read(master, 65536).decode('utf-8')

				assert '\033[1;32m✔\033[0m Completed' in output
				assert '\033[1A\r\033[2K\033[1;32m✔\033[0m Verified' in output
		finally:
			os.close(master)

	# The asynchronous form has the same result as a synchronous context.
	# ----------------------------------------------------------------------
	@classmethod
	def test_async(cls):
		stream = StringIO()
		asyncio.run(cls._run_async(stream))
		assert stream.getvalue() == '✔ Ready\n'

	# Report skipped work through the same default progress stream.
	# ----------------------------------------------------------------------
	@classmethod
	def test_skipped(cls):
		stream = StringIO()

		with redirect_stderr(stream):
			almasi.Progress.skipped('Saved')

		assert stream.getvalue() == '✔ Saved — skipped\n'
