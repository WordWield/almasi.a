# ==============================================================================
# RESOURCE
# ==============================================================================
# PURPOSE:
# Define the source-independent read and subscription contract.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: The common read and observation interface.
# Delegates: Reading, range support and observation to concrete sources.
# ==============================================================================


from .module import Module


class Resource(Module):

	# ==========================================================================
	# PUBLIC METHODS
	# ==========================================================================

	# Read the resource through its concrete source.
	# ----------------------------------------------------------------------
	def read(
		self,
		position : int | None = None,
		length   : int | None = None
	):
		raise NotImplementedError

	# Subscribe to changes through its concrete source.
	# ----------------------------------------------------------------------
	def subscribe(self, callback):
		raise NotImplementedError
