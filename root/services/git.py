# ==============================================================================
# GIT SERVICE
# ==============================================================================
# PURPOSE:
# Provide reusable Git checkout operations to Almasi libraries.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: The public Core Git interface.
# Delegates: Checkout operations to the installer's shared implementation.
# ==============================================================================

from almasi import a, _git


_Git = getattr(_git, '_Git', None) or _git.Git


class Git(_Git, a.Module):

	'''Git checkout operations inherited without an additional execution layer.'''
