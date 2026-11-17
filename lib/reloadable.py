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

	_records   = {}
	_listeners = {}

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

	# Replace the class, then tell every subscriber about each live instance.
	# ----------------------------------------------------------------------
	@classmethod
	def _refresh(cls, record):
		current = record['target']
		target  = current() if issubclass(current, Service) else current
		fresh   = target.__reload__()
		new     = type(fresh) if isinstance(fresh, Service) else fresh

		listeners = Reloadable._listeners.pop(current, ())
		Reloadable._listeners.setdefault(new, []).extend(listeners)
		record['target'] = new

		for instance in gc.get_objects():
			if type(instance) is new:
				Reloadable._notify(instance)

	# Report constructed and reloaded instances to observers of their classes.
	# ----------------------------------------------------------------------
	@classmethod
	def _notify(cls, instance):
		for base in type(instance).__mro__:
			for callback in tuple(Reloadable._listeners.get(base, ())):
				try:
					callback(instance)
				except Exception:
					logging.exception('Reloadable callback failed')

	# ==========================================================================
	# FRAMEWORK METHODS
	# ==========================================================================

	# Register a callback invoked on initial construction and after source reload.
	# ----------------------------------------------------------------------
	@classmethod
	def __on_reload__(cls, callback):
		if not callable(callback):
			raise TypeError('Reload callback must be callable')

		listeners = Reloadable._listeners.setdefault(cls, [])
		if callback not in listeners:
			listeners.append(callback)


class ReloadableModule(Reloadable, Module):
	pass


class ReloadableService(Reloadable, Service):
	pass
