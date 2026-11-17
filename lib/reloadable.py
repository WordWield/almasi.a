# ==============================================================================
# RELOADABLE
# ==============================================================================
# Track opt-in source changes without interrupting executing Python methods.
# ==============================================================================

import gc
import logging
import os

from .module       import Module
from .service      import Service
from .subscription import Subscription


class Reloadable:

	_records   = {}
	_listeners = {}

	# ==========================================================================
	# PRIVATE METHODS
	# ==========================================================================

	# Share one source subscription across replacements of the same class.
	# ----------------------------------------------------------------------
	@classmethod
	def _observe(cls, file):
		key    = (id(file._namespace_lib), file.get_path())
		record = Reloadable._records.get(key)

		if record is None:
			record = {'target': cls, 'pending': False, 'subscription': None}

			def changed(changes):
				if os.path.isfile(file.get_path()):
					record['pending'] = True

			record['subscription'] = file.subscribe(changed)
			Reloadable._records[key] = record

		return record

	# Stop one class-owned lifecycle subscription.
	# ----------------------------------------------------------------------
	@classmethod
	def _cancel_subscription(cls, subscription):
		if subscription._active:
			subscription._active = False
			Reloadable._listeners[cls].remove(subscription)

	# Report a ready instance to listeners registered on its class or ancestors.
	# ----------------------------------------------------------------------
	@classmethod
	def _notify(cls, instance):
		for base in type(instance).__mro__:
			for subscription in tuple(Reloadable._listeners.get(base, ())):
				if subscription._active:
					try:
						subscription._callback(instance)
					except Exception:
						logging.exception('Reloadable callback failed')

	# ==========================================================================
	# FRAMEWORK METHODS
	# ==========================================================================

	# Subscribe to newly constructed and successfully reloaded instances.
	# The returned subscription can be canceled; callbacks receive an instance.
	# ----------------------------------------------------------------------
	@classmethod
	def __on_reload__(cls, callback):
		if not callable(callback):
			raise TypeError('Reload callback must be callable')

		subscription = Subscription(cls, None, callback)
		Reloadable._listeners.setdefault(cls, []).append(subscription)

		return subscription

	# ==========================================================================
	# PUBLIC METHODS
	# ==========================================================================

	# Apply observed source changes only after affected executions have settled.
	# ----------------------------------------------------------------------
	@classmethod
	def apply_pending(cls):
		updated = []

		for record in tuple(Reloadable._records.values()):
			if record['pending']:
				current = record['target']
				target  = current() if issubclass(current, Service) else current
				fresh   = target.__reload__()
				new     = type(fresh) if isinstance(fresh, Service) else fresh

				# Keep class-specific listeners when the Python class is replaced.
				# --------------------------------------------------------------
				listeners = Reloadable._listeners.pop(current, ())
				for subscription in listeners:
					subscription._source = new
				Reloadable._listeners.setdefault(new, []).extend(listeners)

				record['target']  = new
				record['pending'] = False
				updated.append(new)

				# Module.__reload__ has already moved live objects to the new class.
				# --------------------------------------------------------------
				for instance in gc.get_objects():
					if type(instance) is new:
						Reloadable._notify(instance)

		return updated


class ReloadableModule(Reloadable, Module):
	pass


class ReloadableService(Reloadable, Service):
	pass
