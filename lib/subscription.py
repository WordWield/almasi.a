# ==============================================================================
# SUBSCRIPTION
# ==============================================================================
# Own one cancellable registration and its replaceable identifier scope.
# ==============================================================================


class Subscription:

	# ==========================================================================
	# FRAMEWORK METHODS
	# ==========================================================================

	# Retain the source and a snapshot of the initial observation scope.
	# ----------------------------------------------------------------------
	def __init__(self, source, identifiers, callback):
		self._source      = source
		self._identifiers = identifiers
		self._callback    = callback
		self._active      = True

	# ==========================================================================
	# PUBLIC METHODS
	# ==========================================================================

	# Replace only this registration's identifiers, preserving its callback.
	# ----------------------------------------------------------------------
	def update(self, identifiers):
		self._source._update_subscription(self, identifiers)

	# Stop future deliveries without waiting for a running callback.
	# ----------------------------------------------------------------------
	def cancel(self):
		self._source._cancel_subscription(self)
