# ==============================================================================
# SUBSCRIBABLE SERVICE
# ==============================================================================
# Share subscription ownership and change matching across producer services.
# Preserve each producer's own worker and callback execution context.
# ==============================================================================

import logging
import threading

from .service      import Service
from .subscription import Subscription


class Subscribable(Service):

	# ==========================================================================
	# FRAMEWORK METHODS
	# ==========================================================================

	# Attach registration state to the existing concrete service singleton.
	# ----------------------------------------------------------------------
	def __new__(cls):
		instance = super().__new__(cls)

		if '_subscriptions' not in instance.__dict__:
			instance._subscription_lock = threading.RLock()
			instance._subscriptions     = set()

		return instance

	# ==========================================================================
	# PRIVATE METHODS
	# ==========================================================================

	# Normalize a watch scope without retaining the caller's mutable set.
	# ----------------------------------------------------------------------
	def _scope(self, identifiers):
		scope = None

		if identifiers is not None:
			if isinstance(identifiers, (set, frozenset)):
				scope = frozenset(identifiers)
			else:
				raise TypeError('Subscription identifiers must be a set, frozenset or None')

		return scope

	# Replace a live subscription's scope atomically with dispatch snapshots.
	# ----------------------------------------------------------------------
	def _update_subscription(self, subscription, identifiers):
		scope = self._scope(identifiers)

		with self._subscription_lock:
			if subscription._active:
				subscription._identifiers = scope
			else:
				raise RuntimeError('Cannot update a canceled subscription')

	# Cancel an individual registration without waiting for callbacks.
	# ----------------------------------------------------------------------
	def _cancel_subscription(self, subscription):
		with self._subscription_lock:
			subscription._active = False
			self._subscriptions.discard(subscription)

	# Deliver one batch using a stable scope snapshot and no callback lock.
	# ----------------------------------------------------------------------
	def _dispatch(self, changed):
		changes = self._scope(changed)

		with self._subscription_lock:
			snapshot = tuple(
				(subscription, subscription._identifiers)
				for subscription in self._subscriptions
			)

		for subscription, identifiers in snapshot:
			matching = None if changes is None else (
				changes if identifiers is None else changes & identifiers
			)

			if changes is None or matching:
				with self._subscription_lock:
					active = subscription._active

				if active:
					try:
						subscription._callback(matching)
					except Exception:
						logging.exception('Subscription callback failed')

	# ==========================================================================
	# PUBLIC METHODS
	# ==========================================================================

	# Subscribe to all changes or to an explicit set of changed identifiers.
	# ----------------------------------------------------------------------
	def subscribe(self, identifiers=None, callback=None):
		if callable(identifiers) and callback is None:
			callback    = identifiers
			identifiers = None

		if not callable(callback):
			raise TypeError('Subscription callback must be callable')

		scope        = self._scope(identifiers)
		subscription = Subscription(self, scope, callback)

		with self._subscription_lock:
			self._subscriptions.add(subscription)

		return subscription
