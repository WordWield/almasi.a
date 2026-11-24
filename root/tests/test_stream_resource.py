# ==============================================================================
# TEST STREAM RESOURCE
# ==============================================================================
# PURPOSE:
# Verify real temporary-file streams, independent readers and bounded history.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Assertions for the public stream and subscription contracts.
# Delegates: Storage and synchronization to Stream.
# ==============================================================================

import os
from concurrent.futures import ThreadPoolExecutor
from functools          import partial
from unittest           import TestCase
from unittest.mock      import Mock

from almasi import a


class TestStreamResource(a.Tester):

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Read one independent range while another thread writes to the stream.
	# ----------------------------------------------------------------------
	@classmethod
	def _read_repeatedly(cls, resource, position, expected):
		for _ in range(100):
			assert resource.read(position, len(expected)) == expected

	# Record the state visible when a notification is delivered.
	# ----------------------------------------------------------------------
	@classmethod
	def _record(cls, resource, events, changed):
		events.append((resource.read(), resource.closed))

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Verify defaults, boundaries and independent readers of one real file.
	# ----------------------------------------------------------------------
	@classmethod
	def test_ranges(cls):
		resource = a.resources.Stream()

		assert isinstance(resource, a.Resource)
		assert resource.read() == b''
		assert resource.start_position == resource.end_position == 0

		resource.write(b'abc')
		resource.write(b'def')

		assert resource.read() == b'abcdef'
		assert resource.read(position=2) == b'cdef'
		assert resource.read(length=2) == b'ab'
		assert resource.read(2, 3) == b'cde'
		assert resource.read(0, 0) == b''
		assert resource.read(6, 2) == b''
		assert resource.read(5, 8) == b'f'
		assert resource.read(100) == b''
		assert resource.read(2, 3) == b'cde'
		assert resource.start_position == 0
		assert resource.end_position == 6

	# Reject invalid coordinates, input types and retention limits.
	# ----------------------------------------------------------------------
	@classmethod
	def test_invalid_ranges(cls):
		resource = a.resources.Stream()

		for position, length in ((-1, None), (0, -1), ('1', None), (True, None), (0, 1.5)):
			with TestCase().assertRaises(ValueError):
				resource.read(position, length)

		for max_bytes in (0, -1, True, 1.5):
			with TestCase().assertRaises(ValueError):
				a.resources.Stream(max_bytes=max_bytes)

		with TestCase().assertRaises(TypeError):
			resource.write('not bytes')

		assert resource.end_position == 0

	# Independent registrations remain on their own stream and can be canceled.
	# ----------------------------------------------------------------------
	@classmethod
	def test_subscriptions(cls):
		resource = a.resources.Stream()
		other    = a.resources.Stream()
		callback = Mock()

		first  = resource.subscribe(callback)
		second = resource.subscribe(callback)
		third  = other.subscribe(callback)

		try:
			resource.write(b'a')
			assert callback.call_count == 2

			resource.unsubscribe(first)
			resource.unsubscribe(first)
			resource.write(b'b')
			assert callback.call_count == 3

			other.write(b'c')
			assert callback.call_count == 4

			resource.unsubscribe(second)
			resource.write(b'd')
			assert callback.call_count == 4
			assert resource.read() == b'abd'
			assert other.read() == b'c'
		finally:
			resource.unsubscribe(first)
			resource.unsubscribe(second)
			other.unsubscribe(third)

	# Retain the latest absolute byte range without growing the backing file.
	# ----------------------------------------------------------------------
	@classmethod
	def test_bounded_history(cls):
		resource = a.resources.Stream(max_bytes=5)

		for data, start, end, expected in (
			(b'abc',       0,  3, b'abc'),
			(b'defg',      2,  7, b'cdefg'),
			(b'012345678', 11, 16, b'45678'),
			(b'9',         12, 17, b'56789')
		):
			resource.write(data)

			assert resource.start_position == start
			assert resource.end_position == end
			assert resource.read(start) == expected
			assert resource.read(start + 1, 2) == expected[1:3]
			assert os.fstat(resource._file.fileno()).st_size <= 5

		with TestCase().assertRaises(ValueError):
			resource.read(11, 1)

	# Closing announces EOF once, does not discard content or accept more data.
	# ----------------------------------------------------------------------
	@classmethod
	def test_close(cls):
		resource = a.resources.Stream()
		callback = Mock()
		subscription = resource.subscribe(callback)

		try:
			assert not resource.closed
			resource.write(b'')
			assert callback.call_count == 0

			resource.write(b'output')
			resource.close()
			resource.close()

			assert resource.closed
			assert resource.read() == b'output'
			assert resource.end_position == 6
			assert callback.call_count == 2

			with TestCase().assertRaises(ValueError):
				resource.write(b'late')
		finally:
			resource.unsubscribe(subscription)

	# Read binary data concurrently while the producer appends further bytes.
	# ----------------------------------------------------------------------
	@classmethod
	def test_concurrent_ranges(cls):
		resource = a.resources.Stream()
		data     = bytes(range(256)) * 4096
		resource.write(data)

		with ThreadPoolExecutor(max_workers=3) as executor:
			first  = executor.submit(cls._read_repeatedly, resource, 1, data[1:1025])
			second = executor.submit(cls._read_repeatedly, resource, 4095, data[4095:8191])

			for _ in range(10):
				resource.write(data)

			first.result()
			second.result()

		assert resource.end_position == len(data) * 11
		assert resource.read(len(data) * 10) == data

	# Notify only after readers can observe the published bytes and EOF.
	# ----------------------------------------------------------------------
	@classmethod
	def test_notification_visibility(cls):
		resource = a.resources.Stream()
		events   = []
		subscription = resource.subscribe(partial(cls._record, resource, events))

		try:
			resource.write(b'abc')
			resource.close()
			assert events == [(b'abc', False), (b'abc', True)]
		finally:
			resource.unsubscribe(subscription)


if __name__ == '__main__':
	TestStreamResource.run()
