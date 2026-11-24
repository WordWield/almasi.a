# ==============================================================================
# SUBSCRIPTION
# ==============================================================================
# PURPOSE:
# Represent one independently cancellable resource listener.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: The resource and callback of this registration.
# Delegates: Registration lifetime to Resource.
# ==============================================================================


class Subscription:

	# ======================================================================
	# FRAMEWORK METHODS
	# ======================================================================

	# Bind one callback to its resource.
	# ----------------------------------------------------------------------
	def __init__(self, resource, callback):
		self.resource = resource
		self.callback = callback

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Stop future deliveries without waiting for a running callback.
	# ----------------------------------------------------------------------
	def cancel(self):
		self.resource.unsubscribe(self)
