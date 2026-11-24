# ==============================================================================
# TEST WRITABLE
# ==============================================================================
# PURPOSE:
# Verify independent in-memory values and inherited change notifications.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Assertions about the public Writable contract.
# Delegates: State storage and delivery to the resource.
# ==============================================================================

from unittest.mock import Mock

import almasi


class TestWritable(almasi.Tester):

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Check repeated reads, separate values and one notification per write.
	# ----------------------------------------------------------------------
	@classmethod
	def test_write(cls):
		resource = almasi.resources.Writable()
		other    = almasi.resources.Writable(7)
		callback = Mock()

		subscription = resource.subscribe(callback)

		try:
			assert resource.read() is None
			resource.write(3)
			resource.write(3)
			assert resource.read() == resource.read() == 3
			assert other.read() == 7
			assert callback.call_count == 2

			resource.unsubscribe(subscription)
			resource.write(None)
			assert resource.read() is None
			assert callback.call_count == 2
		finally:
			resource.unsubscribe(subscription)
