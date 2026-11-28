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

		self._cache = []
		self._hash  = None

		self._load_method = load_method
		self._hash_method = hash_method

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Forget content after a successful filesystem mutation.
	# ----------------------------------------------------------------------
	def invalidate(self):
		self._cache = []
		self._hash  = None

	# Preserve the established public carrier-type predicate.
	# ----------------------------------------------------------------------
	def is_directory(self):
		return False

	# Publish only completed loads. Invalidation replaces the cache generation,
	# so an in-flight load cannot restore an invalidated cache.
	# ----------------------------------------------------------------------
	def load(self):
		cache = self._cache

		if cache:
			result = cache[0]
		elif self._load_method is not None:
			result = self._load_method()
			owner  = result if isinstance(result, type) else type(result)

			if hasattr(owner, '__on_load__'):
				owner.__on_load__(self)

			cache[:] = [result]
		else:
			result = None

		return result

	# Read the file through its memoized format loader.
	# ----------------------------------------------------------------------
	def read(self):
		return self.load()
