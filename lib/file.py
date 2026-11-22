# ==============================================================================
# FILE
# ==============================================================================
# Load and memoize content for a filesystem resource.
# ==============================================================================

from .filesystem_resource import FilesystemResource


class File(FilesystemResource):

	# ==========================================================================
	# FRAMEWORK METHODS
	# ==========================================================================

	# Keep file-specific content state separate from shared resource identity.
	# --------------------------------------------------------------------------
	def __init__(self, lib, path, route, load_method=None, hash_method=None):
		super().__init__(lib, path, route)

		self._data   = None
		self._hash   = None
		self._loaded = False

		self._load_method = load_method
		self._hash_method = hash_method

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Forget content after a successful filesystem mutation.
	# ----------------------------------------------------------------------
	def _invalidate(self):
		self._data   = None
		self._hash   = None
		self._loaded = False

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Preserve the established public carrier-type predicate.
	# ----------------------------------------------------------------------
	def is_directory(self):
		return False

	# Preserve the current result when an on-load observer invalidates the cache.
	# ----------------------------------------------------------------------
	def load(self):
		if not self._loaded and self._load_method is not None:
			result       = self._load_method()
			self._data   = result
			self._loaded = True
			owner        = result if isinstance(result, type) else type(result)

			if hasattr(owner, '__on_load__'):
				try:
					owner.__on_load__(self)
				except BaseException:
					self._invalidate()
					raise
		else:
			result = self._data

		return result
