# ==============================================================================
# RESOURCE
# ==============================================================================
# PURPOSE:
# Provide one read and change subscription contract for resources.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Subscriber registrations and delivery.
# Delegates: Reading and external change detection to concrete producers.
# ==============================================================================

import logging

from .module import Module


class Resource(Module):

	_observe       = None
	_subscriptions = None

	# ======================================================================
	# FRAMEWORK METHODS
	# ======================================================================

	# Allow a producer to track the lifetime of a notification-only resource.
	# ----------------------------------------------------------------------
	def __init__(self, observe=None):
		self._observe = observe

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

	# Tell an external detector whether this resource needs observation.
	# ----------------------------------------------------------------------
	def is_subscribed(self):
		return bool(self._subscriptions)

	# Register an independent listener and establish external observation.
	# ----------------------------------------------------------------------
	def subscribe(self, callback):
		if callable(callback):
			subscription_id = object()
			listeners       = self.__dict__.setdefault('_subscriptions', {})
			listeners[subscription_id] = callback

			if self._observe is not None:
				try:
					self._observe(self)
				except BaseException:
					listeners.pop(subscription_id, None)
					raise
		else:
			raise TypeError('Subscription callback must be callable')

		return subscription_id

	# Remove one listener and release observation after the last listener.
	# ----------------------------------------------------------------------
	def unsubscribe(self, subscription_id):
		if self._subscriptions:
			callback = self._subscriptions.pop(subscription_id, None)

			if callback is not None and self._observe is not None:
				self._observe(self)

	# Deliver a change to one live registration without consuming content.
	# ----------------------------------------------------------------------
	def notify_subscription(self, subscription_id, changed):
		callback = (self._subscriptions or {}).get(subscription_id)

		if callback is not None:
			try:
				callback(changed)
			except Exception:
				if self._observe is not None:
					logging.exception('Subscription callback failed')
				else:
					raise

	# Notify live listeners in registration order.
	# ----------------------------------------------------------------------
	def update(self, changed=None):
		for subscription_id in tuple(self._subscriptions or ()):
			self.notify_subscription(subscription_id, changed)
