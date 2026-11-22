# ==============================================================================
# ALMASI LIBRARY NAMESPACE
# ==============================================================================
# Resolve Almasi libraries through the core services without global hooks.
# ==============================================================================

import a


# Resolve a missing library through the canonical Almasi service.
# ----------------------------------------------------------------------
def __getattr__(name):
	if a._is_valid_library_name(name):
		result = a.services.Libraries.imp(name)
	else:
		raise AttributeError(f'Module almasi has no attribute {name!r}')

	return result
