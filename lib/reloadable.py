# ==============================================================================
# RELOADABLE
# ==============================================================================
# Track opt-in source changes without interrupting executing Python methods.
# ==============================================================================

import os

from .module  import Module
from .service import Service


class Reloadable:

	_records = {}

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

				record['target']  = new
				record['pending'] = False
				updated.append(new)

		return updated


class ReloadableModule(Reloadable, Module):
	pass


class ReloadableService(Reloadable, Service):
	pass
