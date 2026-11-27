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

		self._cache = None
		self._hash  = None

		self._load_method = load_method
		self._hash_method = hash_method

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Forget content after a successful filesystem mutation.
	# ----------------------------------------------------------------------
	def invalidate(self):
		self._cache = None
		self._hash  = None

	# Preserve the established public carrier-type predicate.
	# ----------------------------------------------------------------------
	def is_directory(self):
		return False

	# Keep the loaded result independent of invalidation during source setup.
	# A single cache entry distinguishes unloaded from a legitimate null result.
	# ----------------------------------------------------------------------
	def load(self):
		cached = self._cache

		if cached is not None:
			result = cached[0]
		elif self._load_method is not None:
			result      = self._load_method()
			cached      = (result,)
			self._cache = cached
			owner       = result if isinstance(result, type) else type(result)

			try:
				if hasattr(owner, '__on_load__'):
					owner.__on_load__(self)
			except BaseException:
				if self._cache is cached:
					self.invalidate()

				raise
		else:
			result = None

		return result

	# Read the file through its memoized format loader.
	# ----------------------------------------------------------------------
	def read(self):
		return self.load()
