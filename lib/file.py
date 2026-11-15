# ==============================================================================
# FILE
# ==============================================================================
# Load and memoize content for a filesystem resource.
# ==============================================================================

from .resource import Resource


class File(Resource):

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

	# Memoize legitimate null values as well as other plugin results.
	# ----------------------------------------------------------------------
	def load(self):
		if not self._loaded and self._load_method is not None:
			self._data   = self._load_method()
			self._loaded = True

		return self._data
