# ==============================================================================
# REFLECTION META
# ==============================================================================
# PURPOSE:
# Resolve Python source modules from class namespaces.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Python module lookup without library-specific conventions.
# Delegates: Interpretation of module metadata to its consumers.
# ==============================================================================

import sys


class ReflectionMeta(type):

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Get module object
	# ----------------------------------------------------------------------
	@classmethod
	def module(mcls, namespace):
		return sys.modules.get(namespace.get('__module__'))
