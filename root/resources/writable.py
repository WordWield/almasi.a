# ==============================================================================
# WRITABLE
# ==============================================================================
# PURPOSE:
# Hold a writable in-memory value and notify listeners after each write.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: The writable resource value.
# Delegates: Subscription registrations and notification delivery to Resource.
# ==============================================================================

import almasi


class Writable(almasi.Resource):

	# ======================================================================
	# FRAMEWORK METHODS
	# ======================================================================

	# Initialize an independent value.
	# ----------------------------------------------------------------------
	def __init__(self, value=None):
		self._value = value

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Read the latest written value without invalidation.
	# ----------------------------------------------------------------------
	def read(self):
		return self._value

	# Update the value and notify listeners through the existing contract.
	# ----------------------------------------------------------------------
	def write(self, value):
		self._value = value
		self.update()
