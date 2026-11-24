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

from .module       import Module
from .subscription import Subscription


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
			subscription = Subscription(self, callback)
			listeners    = self.__dict__.setdefault('_subscriptions', {})
			listeners[subscription] = True

			if self._observe is not None:
				try:
					self._observe(self)
				except BaseException:
					self._subscriptions.pop(subscription, None)
					raise
		else:
			raise TypeError('Subscription callback must be callable')

		return subscription

	# Remove one listener and release observation after the last listener.
	# ----------------------------------------------------------------------
	def unsubscribe(self, subscription):
		if self._subscriptions and self._subscriptions.pop(subscription, None):
			if self._observe is not None:
				self._observe(self)

	# Notify live listeners in registration order without consuming content.
	# ----------------------------------------------------------------------
	def update(self, changed=None, *args):
		subscriptions = self._subscriptions

		if subscriptions:
			args = (changed, *args)

			for subscription in tuple(subscriptions):
				if subscription in subscriptions:
					try:
						subscription.callback(*args)
					except Exception:
						if self._observe is not None:
							logging.exception('Subscription callback failed')
						else:
							raise
