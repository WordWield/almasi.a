# ==============================================================================
# LOG
# ==============================================================================
# PURPOSE:
# Add a timestamp coordinate to a live byte stream using a temporary index.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Timestamp ordering, index retention and time-based reads.
# Delegates: Byte storage, synchronization and notifications to Stream.
# ==============================================================================

import tempfile
from math   import isfinite
from struct import Struct
from time   import time

from almasi import a


class Log(a.resources.Stream):

	_ENTRY = Struct('<dQ')

	# ======================================================================
	# FRAMEWORK METHODS
	# ======================================================================

	# Retain timestamp coordinates independently of the byte file.
	# ----------------------------------------------------------------------
	def __init__(self, max_bytes: int | None = None):
		super().__init__(max_bytes=max_bytes)

		self._index       = tempfile.TemporaryFile(mode='w+b')
		self._entry_count = 0

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Reuse index slots when the byte retention limit bounds entry count.
	# ----------------------------------------------------------------------
	def _seek_entry(self, index: int):
		if self._max_bytes is not None:
			index %= self._max_bytes

		self._index.seek(index * self._ENTRY.size)

	# Read one timestamp and exclusive byte end under the storage lock.
	# ----------------------------------------------------------------------
	def _entry(self, index: int) -> tuple[float, int]:
		self._seek_entry(index)

		return self._ENTRY.unpack(self._index.read(self._ENTRY.size))

	# Find the first indexed coordinate not smaller than the requested one.
	# ----------------------------------------------------------------------
	def _find_entry(self, value, coordinate: int, first: int) -> int:
		last = self._entry_count

		while first < last:
			middle = (first + last) // 2

			if self._entry(middle)[coordinate] < value:
				first = middle + 1
			else:
				last = middle

		return first

	# Index each nonempty write before the shared storage lock is released.
	# ----------------------------------------------------------------------
	def _append(self, data: bytes):
		timestamp = time()

		if self._entry_count:
			timestamp = max(timestamp, self._entry(self._entry_count - 1)[0])

		super()._append(data)

		self._seek_entry(self._entry_count)
		self._index.write(self._ENTRY.pack(timestamp, self.end_position))
		self._index.flush()

		self._entry_count += 1

	# Select retained writes and read their bytes under the same lock.
	# ----------------------------------------------------------------------
	def _read_since(self, since: float | None) -> dict:
		with self._lock:
			first = 0

			if self._max_bytes is not None:
				first = max(0, self._entry_count - self._max_bytes)

			first = self._find_entry(self.start_position + 1, 1, first)
			index = first if since is None else self._find_entry(since, 0, first)

			log            = []
			last_timestamp = since

			if index < self._entry_count:
				position = self.start_position if index == first else self._entry(index - 1)[1]
				data     = self._read(position, None)

				offset = 0

				for entry in range(index, self._entry_count):
					timestamp, end = self._entry(entry)
					next_offset    = end - position

					log.append({'timestamp': timestamp, 'data': data[offset:next_offset]})

					offset         = next_offset
					last_timestamp = timestamp

		return {
			'log'            : log,
			'last_timestamp' : last_timestamp
		}

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Preserve byte reads; an explicit since selects the timestamp coordinate.
	# ----------------------------------------------------------------------
	def read(
		self,
		position : int | None = None,
		length   : int | None = None,
		*,
		since = a.Undefined
	) -> bytes | dict:
		if since is a.Undefined:
			result = super().read(position, length)
		else:
			if position is None and length is None:
				if since is None or (type(since) in (int, float) and isfinite(since)):
					result = self._read_since(since)
				else:
					raise ValueError('since must be a finite Unix timestamp or None')
			else:
				raise ValueError('Byte and timestamp coordinates cannot be combined')

		return result
