# ==============================================================================
# ALMASI LIBRARY NAMESPACE
# ==============================================================================
# Resolve qualified Almasi libraries on first access without import hooks.
# ==============================================================================

import a


Libraries = a.Libraries


# Resolve requested libraries through the canonical Libraries service.
# ----------------------------------------------------------------------
def __getattr__(name):
	if not a._is_valid_library_name(name):
		raise AttributeError(f'Module almasi has no attribute {name!r}')

	return Libraries.imp(name)
