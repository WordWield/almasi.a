# ==============================================================================
# STREAM
# ==============================================================================
# PURPOSE:
# Store a live byte stream in a temporary file with independent range reads.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Retention, byte coordinates, storage and the end of input.
# Delegates: Subscriber registration and notification delivery to Resource.
# ==============================================================================

import tempfile
from threading import Lock

import almasi


class Stream(almasi.Resource):

	# ======================================================================
	# FRAMEWORK METHODS
	# ======================================================================

	# Retain all bytes or reuse a fixed-size file for the latest byte range.
	# ----------------------------------------------------------------------
	def __init__(self, max_bytes: int | None = None):
		if max_bytes is None or (type(max_bytes) is int and max_bytes > 0):
			super().__init__()

			self._file      = tempfile.TemporaryFile(mode='w+b')
			self._lock      = Lock()
			self._max_bytes = max_bytes

			self._end_position = 0
			self._closed       = False
		else:
			raise ValueError('max_bytes must be a positive integer or None')

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Read one available range without consuming bytes or exposing file offsets.
	# ----------------------------------------------------------------------
	def _read(self, position: int, length: int | None) -> bytes:
		with self._lock:
			if position >= self.start_position:
				available = max(0, self.end_position - position)
				size      = available if length is None else min(length, available)
				result    = b''

				if size:
					offset = position
					first  = size

					if self._max_bytes is not None:
						offset %= self._max_bytes
						first   = min(size, self._max_bytes - offset)

					self._file.seek(offset)
					result = self._file.read(first)

					if first < size:
						self._file.seek(0)
						result += self._file.read(size - first)
			else:
				raise ValueError('Stream position is no longer retained')

		return result

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Report the earliest retained absolute byte position.
	# ----------------------------------------------------------------------
	@property
	def start_position(self) -> int:
		position = 0

		if self._max_bytes is not None:
			position = max(0, self._end_position - self._max_bytes)

		return position

	# Report the exclusive end of all bytes ever written.
	# ----------------------------------------------------------------------
	@property
	def end_position(self) -> int:
		return self._end_position

	# Report whether the producer has finished writing.
	# ----------------------------------------------------------------------
	@property
	def closed(self) -> bool:
		return self._closed

	# Read without advancing a resource-owned or subscription-owned cursor.
	# ----------------------------------------------------------------------
	def read(
		self,
		position : int | None = None,
		length   : int | None = None
	) -> bytes:
		if position is None:
			position = 0

		if type(position) is int and position >= 0:
			if length is None or (type(length) is int and length >= 0):
				result = self._read(position, length)
			else:
				raise ValueError('length must be a non-negative integer or None')
		else:
			raise ValueError('position must be a non-negative integer or None')

		return result

	# Publish bytes only after the file and absolute coordinates are updated.
	# ----------------------------------------------------------------------
	def write(self, data: bytes) -> None:
		with self._lock:
			if not self._closed:
				if isinstance(data, bytes):
					if data:
						end    = self._end_position + len(data)
						offset = self._end_position

						if self._max_bytes is not None:
							data   = data[-self._max_bytes:]
							offset = (end - len(data)) % self._max_bytes

						first = len(data)

						if self._max_bytes is not None:
							first = min(first, self._max_bytes - offset)

						self._file.seek(offset)
						self._file.write(memoryview(data)[:first])

						if first < len(data):
							self._file.seek(0)
							self._file.write(memoryview(data)[first:])

						self._file.flush()
						self._end_position = end
				else:
					raise TypeError('Stream data must be bytes')
			else:
				raise ValueError('Stream is closed')

		if data:
			self.update()

	# Finish input once, retaining the file for remaining readers.
	# ----------------------------------------------------------------------
	def close(self) -> None:
		with self._lock:
			changed      = not self._closed
			self._closed = True

		if changed:
			self.update()
