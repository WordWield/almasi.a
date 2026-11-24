# ==============================================================================
# PROCESS
# ==============================================================================
# PURPOSE:
# Own a child process and expose its output and lifecycle as live resources.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Launch, pipe draining, termination and completion.
# Delegates: OS execution to subprocess; history and notifications to resources.
# ==============================================================================

import subprocess
import sys
from functools import partial
from threading import Lock, Thread, current_thread
from typing    import BinaryIO


class Process:

	_CHUNK_SIZE = 65536

	# ======================================================================
	# FRAMEWORK METHODS
	# ======================================================================

	# Allocate stable resources before launching the child.
	# ----------------------------------------------------------------------
	def __init__(
		self,
		command   : str | list[str] | tuple[str, ...],
		cwd       : str | None            = None,
		env       : dict[str, str] | None = None,
		max_bytes : int | None            = None
	):
		resources = sys.modules['almasi'].resources

		self._command = command
		self._cwd     = cwd
		self._env     = env

		self._stdout = resources.Stream(max_bytes=max_bytes)
		self._stderr = resources.Stream(max_bytes=max_bytes)
		self._state  = resources.Writable({'status': 'created', 'returncode': None})

		self._process    = None
		self._monitor    = None
		self._readers    = ()
		self._errors     = []
		self._start_lock = Lock()

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Drain each pipe independently so neither can block the other.
	# ----------------------------------------------------------------------
	def _capture(self, pipe, stream):
		try:
			with pipe:
				for data in iter(partial(pipe.read, self._CHUNK_SIZE), b''):
					stream.write(data)
		except Exception as error:
			self._errors.append(error)
			self._process.kill()
		finally:
			try:
				stream.close()
			except Exception as error:
				self._errors.append(error)

	# Publish completion only after both output streams have reached EOF.
	# ----------------------------------------------------------------------
	def _complete(self):
		returncode = self._process.wait()

		for reader in self._readers:
			reader.join()

		try:
			self._process.stdin.close()
		except OSError as error:
			self._errors.append(error)

		status = 'failed' if self._errors else 'exited'

		try:
			self._state.write({'status': status, 'returncode': returncode})
		except Exception as error:
			self._errors.append(error)

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Expose the child's native binary input pipe after launch.
	# ----------------------------------------------------------------------
	@property
	def stdin(self) -> BinaryIO:
		if self._process is not None:
			result = self._process.stdin
		else:
			raise RuntimeError('Process has not started')

		return result

	# Preserve output resource identity throughout the process lifetime.
	# ----------------------------------------------------------------------
	@property
	def stdout(self):
		return self._stdout

	# Keep diagnostic output independent of ordinary output.
	# ----------------------------------------------------------------------
	@property
	def stderr(self):
		return self._stderr

	# Expose lifecycle changes through the ordinary writable resource.
	# ----------------------------------------------------------------------
	@property
	def state(self):
		return self._state

	# Start one child, without shell interpretation or restart policy.
	# ----------------------------------------------------------------------
	def start(self) -> None:
		with self._start_lock:
			if self._process is None:
				self._process = subprocess.Popen(
					self._command,
					cwd     = self._cwd,
					env     = self._env,
					stdin   = subprocess.PIPE,
					stdout  = subprocess.PIPE,
					stderr  = subprocess.PIPE,
					bufsize = 0
				)

				self._readers = (
					Thread(target=self._capture, args=(self._process.stdout, self._stdout)),
					Thread(target=self._capture, args=(self._process.stderr, self._stderr))
				)
				self._monitor = Thread(target=self._complete)
			else:
				raise RuntimeError('Process has already started')

		try:
			self._state.write({'status': 'running', 'returncode': None})
		finally:
			for reader in self._readers:
				reader.start()

			self._monitor.start()

	# Request termination without blocking the calling thread.
	# ----------------------------------------------------------------------
	def stop(self) -> None:
		if self._process is not None:
			self._process.terminate()

	# Wait for exit, drained output and final state notification.
	# ----------------------------------------------------------------------
	def wait(self, timeout: float | None = None) -> int:
		has_monitor = self._monitor is not None and self._monitor.ident is not None
		is_worker   = current_thread() in (*self._readers, self._monitor)

		if has_monitor and not is_worker:
			self._monitor.join(timeout)

			if not self._monitor.is_alive():
				if not self._errors:
					result = self._process.returncode
				else:
					raise RuntimeError('Process output or notification failed') from self._errors[0]
			else:
				raise subprocess.TimeoutExpired(self._command, timeout)
		else:
			raise RuntimeError('Wait requires a started process outside its callbacks')

		return result
