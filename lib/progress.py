# ==============================================================================
# PROGRESS
# ==============================================================================
# PURPOSE:
# Present a replaceable single-line description of an operation and its outcome.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Progress text, outcome rendering and replacement of the latest line.
# Delegates: Active terminal animation to yaspin; error policy to callers.
# ==============================================================================

import sys

from yaspin import yaspin


class Progress:

	# ======================================================================
	# FRAMEWORK METHODS
	# ======================================================================

	# Keep redirected streams free of animation and terminal control codes.
	# ----------------------------------------------------------------------
	def __init__(self, text: str, stream=None):
		self._stream = sys.stderr if stream is None else stream
		self._text   = text
		self._status = None

		self._spinner = yaspin(text=text, stream=self._stream) if self._stream.isatty() else None

	# Expose the progress object rather than the animation implementation.
	# ----------------------------------------------------------------------
	def __enter__(self):
		if self._spinner is not None:
			self._spinner.__enter__()

		return self

	# Render completion without intercepting the operation's exception.
	# ----------------------------------------------------------------------
	def __exit__(self, exc_type, exc_value, traceback):
		if self._spinner is not None:
			self._spinner.__exit__(exc_type, exc_value, traceback)

		self._status = '✔' if exc_type is None else '❌'
		self._render()

	# Reuse the same context lifecycle in asynchronous operations.
	# ----------------------------------------------------------------------
	async def __aenter__(self):
		return self.__enter__()

	# Keep cancellation and other failures visible to the caller.
	# ----------------------------------------------------------------------
	async def __aexit__(self, exc_type, exc_value, traceback):
		self.__exit__(exc_type, exc_value, traceback)

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Render the current outcome, optionally replacing the previous line.
	# ----------------------------------------------------------------------
	def _render(self, replace=False):
		prefix = '\033[1A\r\033[2K' if replace and self._spinner is not None else ''
		status = self._status

		if status == '✔' and self._spinner is not None:
			status = '\033[1;32m✔\033[0m'

		print(f'{prefix}{status} {self._text}', file=self._stream, flush=True)

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Change active text or replace the latest completed terminal line.
	# ----------------------------------------------------------------------
	def update(self, text: str) -> None:
		self._text = text

		if self._status is not None:
			self._render(replace=True)
		elif self._spinner is not None:
			self._spinner.text = text

	# Report work that was already complete without starting animation.
	# ----------------------------------------------------------------------
	@staticmethod
	def skipped(text: str) -> None:
		print(f'✔ {text} — skipped', file=sys.stderr, flush=True)
