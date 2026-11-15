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
			instance._subscriptions     = {}
			instance._snapshot          = ()
			instance._by_id             = {}
			instance._broad             = set()
			instance._next_order        = 0

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

	# Keep only interested subscriptions under each identifier.
	# ----------------------------------------------------------------------
	def _reindex(self, subscription, before, after):
		if before is None:
			self._broad.discard(subscription)
		else:
			for identifier in before:
				bucket = self._by_id[identifier]
				bucket.discard(subscription)

				if not bucket:
					del self._by_id[identifier]

		if after is None:
			self._broad.add(subscription)
		else:
			for identifier in after:
				self._by_id.setdefault(identifier, set()).add(subscription)

	# Keep a complete immutable view for broad and dense invalidations.
	# ----------------------------------------------------------------------
	def _refresh(self):
		self._snapshot = tuple(
			(subscription, subscription._identifiers)
			for subscription in self._subscriptions
		)

	# Replace a live subscription's scope atomically with dispatch snapshots.
	# ----------------------------------------------------------------------
	def _update_subscription(self, subscription, identifiers):
		scope = self._scope(identifiers)

		with self._subscription_lock:
			if subscription._active:
				self._reindex(subscription, subscription._identifiers, scope)
				subscription._identifiers = scope
				self._refresh()
			else:
				raise RuntimeError('Cannot update a canceled subscription')

	# Cancel an individual registration without waiting for callbacks.
	# ----------------------------------------------------------------------
	def _cancel_subscription(self, subscription):
		with self._subscription_lock:
			if subscription._active:
				subscription._active = False
				self._reindex(subscription, subscription._identifiers, frozenset())
				self._subscriptions.pop(subscription, None)
				self._refresh()

	# Use indexed routing when it is cheaper than the full subscription view.
	# ----------------------------------------------------------------------
	def _dispatch(self, changed):
		changes = changed if changed is None or isinstance(changed, frozenset) else self._scope(changed)

		if changes is None or len(self._snapshot) <= 16:
			candidates = self._snapshot
		elif changes:
			with self._subscription_lock:
				potential = len(self._broad) + sum(
					len(self._by_id.get(identifier, ())) for identifier in changes
				)

				if potential * 2 >= len(self._subscriptions):
					candidates = self._snapshot
				else:
					matched = set(self._broad)

					for identifier in changes:
						matched.update(self._by_id.get(identifier, ()))

					candidates = tuple(
						(subscription, subscription._identifiers)
						for subscription in sorted(matched, key=self._subscriptions.__getitem__)
					)
		else:
			candidates = ()

		for subscription, identifiers in candidates:
			matching = None if changes is None else (
				changes if identifiers is None else changes & identifiers
			)

			if changes is None or matching:
				if subscription._active:
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
			self._subscriptions[subscription] = self._next_order
			self._next_order += 1
			self._reindex(subscription, frozenset(), scope)
			self._refresh()

		return subscription
