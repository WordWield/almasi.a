# ==============================================================================
# RELOADABLE
# ==============================================================================
# Reload source-backed classes and notify consumers of their live instances.
# ==============================================================================

import gc
import logging
import os

from .module  import Module
from .service import Service


class Reloadable:

	_records = {}

	# ==========================================================================
	# PRIVATE METHODS
	# ==========================================================================

	# Watch each source class once and refresh it when its file changes.
	# ----------------------------------------------------------------------
	@classmethod
	def _observe(cls, file):
		key    = (id(file._namespace_lib), file.get_path())
		record = Reloadable._records.get(key)

		if record is None:
			record = {'target': cls, 'subscription': None}
			Reloadable._records[key] = record

			def changed(changes):
				if os.path.isfile(file.get_path()):
					try:
						Reloadable._refresh(record)
					except Exception:
						logging.exception('Reloadable source update failed: %s', file.get_path())

			try:
				record['subscription'] = file.subscribe(changed)
			except BaseException:
				del Reloadable._records[key]
				raise

		return record

	# Replace the class, then report each live instance to its callback.
	# ----------------------------------------------------------------------
	@classmethod
	def _refresh(cls, record):
		current = record['target']
		target  = current() if issubclass(current, Service) else current
		fresh   = target.__reload__()
		new     = type(fresh) if isinstance(fresh, Service) else fresh

		callback = current.__dict__.get('__reload_callback__')
		if callback is not None:
			new.__reload_callback__ = callback

		record['target'] = new

		for instance in gc.get_objects():
			if type(instance) is new:
				Reloadable._notify(instance)

	# Use the nearest callback in the class hierarchy.
	# ----------------------------------------------------------------------
	@classmethod
	def _notify(cls, instance):
		for base in type(instance).__mro__:
			callback = base.__dict__.get('__reload_callback__')

			if callback is not None:
				try:
					callback(instance)
				except Exception:
					logging.exception('Reloadable callback failed')
				break

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
