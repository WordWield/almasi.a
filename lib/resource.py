# ==============================================================================
# RESOURCE
# ==============================================================================
# PURPOSE:
# Define the source-independent read and subscription contract.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Direct resource subscription registrations and notification delivery.
# Delegates: Reading and indexed observation to concrete sources.
# ==============================================================================

from .module       import Module
from .subscription import Subscription


class Resource(Module):

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# End one direct registration when its handle is canceled.
	# ----------------------------------------------------------------------
	def _cancel_subscription(self, subscription):
		subscription._active = False
		self._subscriptions.discard(subscription)

	# Notify live listeners without consuming the resource's content.
	# ----------------------------------------------------------------------
	def _dispatch(self, changed):
		for subscription in tuple(self.__dict__.get('_subscriptions', ())):
			if subscription._active:
				subscription._callback(changed)

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Read the resource through its concrete source.
	# ----------------------------------------------------------------------
	def read(
		self,
		position : int | None = None,
		length   : int | None = None
	):
		raise NotImplementedError

	# Give each direct listener an independent cancellable registration.
	# ----------------------------------------------------------------------
	def subscribe(self, callback):
		subscription = Subscription(self, None, callback)
		self.__dict__.setdefault('_subscriptions', set()).add(subscription)

		return subscription
