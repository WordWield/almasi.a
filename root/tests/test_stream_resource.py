# ==============================================================================
# TEST STREAM RESOURCE
# ==============================================================================
# PURPOSE:
# Verify range normalization and independent non-consuming reads.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Tests of the public stream read contract.
# Delegates: Source storage to a mock byte source.
# ==============================================================================

from unittest.mock import patch

import almasi


class TestStreamResource(almasi.Tester):

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Verify defaults, boundaries and independent readers of one source.
	# ----------------------------------------------------------------------
	@classmethod
	def test_ranges(cls):
		resource = almasi.StreamResource()
		data     = b'abcdef'

		assert isinstance(resource, almasi.Resource)

		with patch.object(resource, '_read', side_effect=lambda position, length: data[position:] if length is None else data[position:position + length]):
			assert resource.read() == data
			assert resource.read(position=2) == b'cdef'
			assert resource.read(length=2) == b'ab'
			assert resource.read(2, 3) == b'cde'
			assert resource.read(0, 0) == b''
			assert resource.read(6, 2) == b''
			assert resource.read(5, 8) == b'f'
			assert resource.read(2, 3) == b'cde'

	# Reject invalid coordinates before requesting data from the source.
	# ----------------------------------------------------------------------
	@classmethod
	def test_invalid_ranges(cls):
		resource = almasi.StreamResource()

		with patch.object(resource, '_read') as source:
			for position, length in ((-1, None), (0, -1), ('1', None), (True, None), (0, 1.5)):
				try:
					resource.read(position, length)
				except ValueError:
					rejected = True
				else:
					rejected = False

				assert rejected

			source.assert_not_called()


if __name__ == '__main__':
	TestStreamResource.run()
