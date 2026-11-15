# ==============================================================================
# RESOURCE
# ==============================================================================
# Define the source-independent read and subscription contract.
# ==============================================================================


class Resource:

	# ==========================================================================
	# PUBLIC METHODS
	# ==========================================================================

	# Read the resource through its concrete source.
	# ----------------------------------------------------------------------
	def read(self):
		raise NotImplementedError

	# Subscribe to changes through its concrete source.
	# ----------------------------------------------------------------------
	def subscribe(self, callback):
		raise NotImplementedError
