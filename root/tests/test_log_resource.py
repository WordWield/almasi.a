# ==============================================================================
# TEST LOG RESOURCE
# ==============================================================================
# PURPOSE:
# Verify timestamp reads, bounded index retention and notification visibility.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Assertions for Log's byte and timestamp contracts.
# Delegates: Storage and subscription delivery to the resource.
# ==============================================================================

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from functools          import partial
from unittest           import TestCase
from unittest.mock      import patch

from almasi import a


class TestLogResource(a.Tester):

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Capture the entire indexed history from a synchronous callback.
	# ----------------------------------------------------------------------
	@classmethod
	def _record(cls, resource, events, changed):
		events.append(resource.read(since=None))

	# Verify coherent timestamp and text snapshots during concurrent writes.
	# ----------------------------------------------------------------------
	@classmethod
	def _read_repeatedly(cls, resource):
		for _ in range(100):
			result = resource.read(since=None)
			text   = ''.join(entry['text'] for entry in result['log'])

			assert text == 'x' * len(text)
			assert result['last_timestamp'] == result['log'][-1]['timestamp']

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Preserve byte reads and include equal timestamps at the read boundary.
	# ----------------------------------------------------------------------
	@classmethod
	def test_timestamps(cls):
		resource = a.resources.Log()
		module   = sys.modules[type(resource).__module__]

		assert isinstance(resource, a.resources.Stream)
		assert resource.read(since=None) == {'log': [], 'last_timestamp': None}

		with patch.object(module, 'time', side_effect=[10.0, 11.0, 11.0, 9.0]):
			resource.write(b'a')
			resource.write(b'')
			resource.write(b'bc')
			resource.write(b'd')
			resource.write(b'e')

		assert resource.read() == b'abcde'
		assert resource.read(1, 2) == b'bc'
		assert resource.read(since=11.0) == {
			'log' : [
				{'timestamp': 11.0, 'text': 'bc'},
				{'timestamp': 11.0, 'text': 'd'},
				{'timestamp': 11.0, 'text': 'e'}
			],
			'last_timestamp': 11.0
		}
		assert resource.read(since=12.0) == {'log': [], 'last_timestamp': 12.0}

	# Preserve original bytes while exposing UTF-8 text at the time coordinate.
	# ----------------------------------------------------------------------
	@classmethod
	def test_text(cls):
		resource = a.resources.Log()
		data     = 'Привет'.encode('utf-8')

		resource.write(data)
		resource.write(b'\xff')
		resource.write(b'\xc3')
		resource.write(b'\xa9')

		assert resource.read() == data + b'\xff\xc3\xa9'
		assert [entry['text'] for entry in resource.read(since=None)['log']] == [
			'Привет', '\ufffd', '\ufffd', '\ufffd'
		]

	# Discard expired entries and keep the retained suffix of partial writes.
	# ----------------------------------------------------------------------
	@classmethod
	def test_retention(cls):
		resource = a.resources.Log(max_bytes=3)
		module   = sys.modules[type(resource).__module__]

		with patch.object(module, 'time', side_effect=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]):
			resource.write(b'abcd')
			resource.write(b'e')
			assert resource.read(since=None)['log'] == [
				{'timestamp': 1.0, 'text': 'cd'},
				{'timestamp': 2.0, 'text': 'e'}
			]

			resource.write(b'f')
			resource.write(b'g')
			resource.write(b'h')
			resource.write(b'i')

		assert resource.read(since=1.0)['log'] == [
			{'timestamp': 4.0, 'text': 'g'},
			{'timestamp': 5.0, 'text': 'h'},
			{'timestamp': 6.0, 'text': 'i'}
		]
		assert resource.read(resource.start_position) == b'ghi'
		assert os.fstat(resource._index.fileno()).st_size <= 3 * 16

	# Expose the completed index before notifying listeners and on EOF.
	# ----------------------------------------------------------------------
	@classmethod
	def test_notifications(cls):
		resource = a.resources.Log()
		events   = []

		subscription = resource.subscribe(partial(cls._record, resource, events))

		try:
			resource.write(b'abc')
			resource.close()
			resource.close()

			assert len(events) == 2
			assert events[0] == events[1] == resource.read(since=None)
			assert events[0]['log'][0]['text'] == 'abc'

			with TestCase().assertRaises(ValueError):
				resource.write(b'late')

			assert len(events) == 2
		finally:
			resource.unsubscribe(subscription)

	# Reject mixed coordinates and nonfinite or invalid timestamps.
	# ----------------------------------------------------------------------
	@classmethod
	def test_invalid_reads(cls):
		resource = a.resources.Log()

		for since in (True, '1', float('nan'), float('inf')):
			with TestCase().assertRaises(ValueError):
				resource.read(since=since)

		with TestCase().assertRaises(ValueError):
			resource.read(0, since=None)

		with TestCase().assertRaises(ValueError):
			resource.read(length=1, since=None)

	# Serialize index and data access while several readers observe a writer.
	# ----------------------------------------------------------------------
	@classmethod
	def test_concurrent_reads(cls):
		resource = a.resources.Log()
		resource.write(b'x')

		with ThreadPoolExecutor(max_workers=3) as executor:
			first  = executor.submit(cls._read_repeatedly, resource)
			second = executor.submit(cls._read_repeatedly, resource)

			for _ in range(100):
				resource.write(b'x')

			first.result()
			second.result()

		assert len(resource.read(since=None)['log']) == 101
		assert resource.read() == b'x' * 101
