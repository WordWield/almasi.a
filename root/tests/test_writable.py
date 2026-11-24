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

from almasi import a


class TestWritable(a.Tester):

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Check repeated reads, separate values and one notification per write.
	# ----------------------------------------------------------------------
	@classmethod
	def test_write(cls):
		resource = a.resources.Writable()
		other    = a.resources.Writable(7)
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
