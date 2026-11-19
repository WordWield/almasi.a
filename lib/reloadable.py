# ==============================================================================
# RELOADABLE
# ==============================================================================
# Observe source changes and notify consumers of live instances.
# ==============================================================================

import gc
import logging
import os

from .module  import Module
from .service import Service


class Reloadable:

	# ==========================================================================
	# PRIVATE METHODS
	# ==========================================================================

	# The observed class owns one subscription, inherited by its replacements.
	# ----------------------------------------------------------------------
	@classmethod
	def _observe_reload(cls, file):
		if '_reload_subscription' not in cls.__dict__:
			def changed(changes):
				nonlocal cls

				if os.path.isfile(file.get_path()):
					try:
						current = cls
						target  = current() if issubclass(current, Service) else current
						fresh   = target.__reload__()
						cls     = type(fresh) if isinstance(fresh, Service) else fresh

						cls._reload_subscription = subscription
						callback = current.__dict__.get('__reload_callback__')
						if callback is not None:
							cls.__reload_callback__ = callback

						for instance in gc.get_objects():
							if type(instance) is cls:
								Reloadable._notify(instance)
					except Exception:
						logging.exception('Reloadable source update failed: %s', file.get_path())

			subscription = file.subscribe(changed)
			cls._reload_subscription = subscription

	# Report an instance to its nearest inherited callback.
	# ----------------------------------------------------------------------
	@classmethod
	def _notify(cls, instance):
		callback = getattr(type(instance), '__reload_callback__', None)
		if callback is not None:
			try:
				callback(instance)
			except Exception:
				logging.exception('Reloadable callback failed')

	# ==========================================================================
	# FRAMEWORK METHODS
	# ==========================================================================

	# Set the sole callback for this class and its inheriting subclasses.
	# ----------------------------------------------------------------------
	@classmethod
	def __on_reload__(cls, callback):
		if not callable(callback):
			raise TypeError('Reload callback must be callable')

		cls.__reload_callback__ = callback


class ReloadableModule(Reloadable, Module):
	pass


class ReloadableService(Reloadable, Service):
	pass
