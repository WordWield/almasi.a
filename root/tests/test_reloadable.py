# ==============================================================================
# TEST RELOADABLE
# ==============================================================================
# Verify deferred source changes and persistent service identity.
# ==============================================================================

import os
import tempfile

from unittest.mock import patch

import a


class TestReloadable(a.Tester):

	# ==========================================================================
	# PUBLIC METHODS
	# ==========================================================================

	# A filesystem change stays pending until a caller-selected quiet boundary.
	# ----------------------------------------------------------------------
	@classmethod
	def test_service_reload(cls):
		with tempfile.TemporaryDirectory(dir=a.__path__, prefix='__reloadable_') as path:
			file_path = os.path.join(path, 'counter.py')
			with open(file_path, 'w', encoding='utf-8') as stream:
				stream.write(
					'import a\nclass Counter(a.ReloadableService):\n'
					'\tdef initialize(self):\n\t\tself.value = 5\n'
					'\tdef read(self):\n\t\treturn self.value + 1\n'
				)

			directory = a.Directory(a, path, 'a.' + os.path.basename(path))
			with patch.object(type(a.services.Filesystem), '_watch', return_value=None):
				service = directory.Counter
				service.initialize()
				assert service.read() == 6

				with open(file_path, 'w', encoding='utf-8') as stream:
					stream.write(
						'import a\nclass Counter(a.ReloadableService):\n'
						'\tdef initialize(self):\n\t\traise AssertionError()\n'
						'\tdef read(self):\n\t\treturn self.value + 2\n'
					)
				a.services.Filesystem._changed_paths(a.__path__, {file_path: 'modified'})
				assert service.read() == 6
				assert a.Reloadable.apply_pending() == [type(service)]
				assert directory.Counter is service
				assert service.read() == 7

				key = (id(a), file_path)
				a.Reloadable._records.pop(key)['subscription'].cancel()


if __name__ == '__main__':
	TestReloadable.run()
