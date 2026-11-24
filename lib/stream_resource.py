# ==============================================================================
# STREAM RESOURCE
# ==============================================================================
# PURPOSE:
# Read finite byte ranges from a stream without consuming shared state.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Range validation and normalization.
# Delegates: Byte retrieval, retention and change observation to the source.
# ==============================================================================

from .resource import Resource


class StreamResource(Resource):

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Retrieve bytes at an absolute position from the concrete source.
	# ----------------------------------------------------------------------
	def _read(self, position: int, length: int | None) -> bytes:
		raise NotImplementedError

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Read without advancing a resource-owned or subscription-owned cursor.
	# ----------------------------------------------------------------------
	def read(
		self,
		position : int | None = None,
		length   : int | None = None
	) -> bytes:
		if position is None:
			position = 0

		if type(position) is int and position >= 0:
			if length is None or (type(length) is int and length >= 0):
				result = self._read(position, length)
			else:
				raise ValueError('length must be a non-negative integer or None')
		else:
			raise ValueError('position must be a non-negative integer or None')

		return result
