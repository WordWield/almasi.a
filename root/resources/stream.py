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

from almasi import a


class Stream(a.Resource):

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

	# Map an absolute range to its first contiguous file segment.
	# ----------------------------------------------------------------------
	def _seek(self, position: int, length: int) -> int:
		if self._max_bytes is not None:
			position %= self._max_bytes
			length    = min(length, self._max_bytes - position)

		self._file.seek(position)

		return length

	# Read retained bytes without exposing or consuming the file cursor.
	# ----------------------------------------------------------------------
	def _read(self, position: int, length: int | None) -> bytes:
		with self._lock:
			if position >= self.start_position:
				available = max(0, self._end_position - position)
				size      = available if length is None else min(available, length)
				result    = b''

				if size:
					first  = self._seek(position, size)
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
		return 0 if self._max_bytes is None else max(0, self._end_position - self._max_bytes)

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
						end = self._end_position + len(data)

						if self._max_bytes is not None:
							data = memoryview(data)[-self._max_bytes:]

						first = self._seek(end - len(data), len(data))
						self._file.write(data[:first])

						if first < len(data):
							self._file.seek(0)
							self._file.write(data[first:])

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
