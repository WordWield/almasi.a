# ==============================================================================
# TEST PROCESS
# ==============================================================================
# PURPOSE:
# Verify real child processes, pipe capture and observable completion.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Assertions about the public Process contract.
# Delegates: Process execution and resource ownership to Process.
# ==============================================================================

import subprocess
import sys
from functools import partial
from threading import Event

from almasi import a


class TestProcess(a.Tester):

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Capture lifecycle transitions through the ordinary resource contract.
	# ----------------------------------------------------------------------
	@classmethod
	def _record_state(cls, process, states, changed):
		states.append(process.state.read())

	# Wake the test as soon as real output becomes available.
	# ----------------------------------------------------------------------
	@classmethod
	def _signal(cls, event, changed):
		event.set()

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Verify stable resource identities, native stdin and final exit status.
	# ----------------------------------------------------------------------
	@classmethod
	def test_lifecycle(cls):
		process = a.Process([sys.executable, '-c', 'import sys; data = sys.stdin.buffer.read(); sys.stdout.buffer.write(data); sys.stderr.buffer.write(b"error"); sys.exit(7)'])
		stdout  = process.stdout
		stderr  = process.stderr
		state   = process.state
		states  = []

		subscription = state.subscribe(partial(cls._record_state, process, states))

		try:
			assert state.read() == {'status': 'created', 'returncode': None}
			assert not isinstance(process, a.Module)
			process.start()

			assert process.stdin.write(b'input') == 5
			process.stdin.close()
			assert process.wait(timeout=10) == 7
			assert process.wait(timeout=10) == 7
			assert process.stdout is stdout
			assert process.stderr is stderr
			assert process.state is state
			assert stdout.read() == b'input'
			assert stderr.read() == b'error'
			assert stdout.closed and stderr.closed
			assert states == [
				{'status': 'running', 'returncode': None},
				{'status': 'exited', 'returncode': 7}
			]
		finally:
			process.stop()
			state.unsubscribe(subscription)

	# Drain more than the OS pipe capacity in both directions without waiting.
	# ----------------------------------------------------------------------
	@classmethod
	def test_large_output(cls):
		process = a.Process([sys.executable, '-c', 'import os; os.write(1, b"a" * 1048576); os.write(2, b"b" * 1048576)'])

		try:
			process.start()
			assert process.wait(timeout=10) == 0
			assert process.stdout.read() == b'a' * 1048576
			assert process.stderr.read() == b'b' * 1048576
		finally:
			process.stop()

	# Terminate a live child after seeing output, retaining its history.
	# ----------------------------------------------------------------------
	@classmethod
	def test_stop(cls):
		process = a.Process([sys.executable, '-u', '-c', 'import time; print("ready"); time.sleep(60)'])
		event   = Event()

		subscription = process.stdout.subscribe(partial(cls._signal, event))

		try:
			process.start()
			assert event.wait(10)
			assert process.stdout.read() == b'ready\n'

			try:
				process.wait(timeout=0)
			except subprocess.TimeoutExpired:
				timed_out = True
			else:
				timed_out = False

			assert timed_out
			process.stop()
			assert process.wait(timeout=10) != 0
			assert process.stdout.closed
			assert process.stderr.closed
			assert process.state.read()['status'] == 'exited'
		finally:
			process.stop()
			process.stdout.unsubscribe(subscription)

	# Reuse the same retention policy independently for both child outputs.
	# ----------------------------------------------------------------------
	@classmethod
	def test_retention(cls):
		process = a.Process(
			[sys.executable, '-c', 'import sys; sys.stdout.write("abcdef"); sys.stderr.write("123456")'],
			max_bytes=3
		)

		try:
			process.start()
			assert process.wait(timeout=10) == 0
			assert process.stdout.start_position == 3
			assert process.stdout.read(3) == b'def'
			assert process.stderr.read(3) == b'456'
		finally:
			process.stop()

	# Reject a second launch without replacing the stable resource identities.
	# ----------------------------------------------------------------------
	@classmethod
	def test_single_launch(cls):
		process = a.Process([sys.executable, '-c', 'print("once")'])

		try:
			process.start()
			assert process.wait(timeout=10) == 0

			try:
				process.start()
			except RuntimeError:
				rejected = True
			else:
				rejected = False

			assert rejected
			assert process.stdout.read() == b'once\n'
		finally:
			process.stop()

	# Surface launch failure without creating a phantom running process.
	# ----------------------------------------------------------------------
	@classmethod
	def test_launch_failure(cls):
		process = a.Process([''])

		try:
			process.start()
		except OSError:
			rejected = True
		else:
			rejected = False

		assert rejected
		assert process.state.read()['status'] == 'created'
