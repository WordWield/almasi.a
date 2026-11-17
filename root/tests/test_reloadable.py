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
				seen   = []
				handle = type(service).__on_reload__(seen.append)

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
				assert seen == [service]
				handle.cancel()

				key = (id(a), file_path)
				a.Reloadable._records.pop(key)['subscription'].cancel()

	# Report initialized instances and retain class-specific listeners after reload.
	# ----------------------------------------------------------------------
	@classmethod
	def test_module_callbacks(cls):
		with tempfile.TemporaryDirectory(dir=a.__path__, prefix='__reloadable_') as path:
			file_path = os.path.join(path, 'handler.py')
			with open(file_path, 'w', encoding='utf-8') as stream:
				stream.write('import a\nclass Handler(a.ReloadableModule):\n\tpass\n')

			directory = a.Directory(a, path, 'a.' + os.path.basename(path))
			with patch.object(type(a.services.Filesystem), '_watch', return_value=None):
				handler = directory.Handler
				seen     = []
				handle  = handler.__on_reload__(seen.append)
				first   = handler()
				second  = handler()

				assert seen == [first, second]

				with open(file_path, 'w', encoding='utf-8') as stream:
					stream.write('import a\nclass Handler(a.ReloadableModule):\n\tversion = 2\n')

				a.services.Filesystem._changed_paths(a.__path__, {file_path: 'modified'})
				assert handler.__dict__.get('version') is None
				a.Reloadable.apply_pending()

				assert seen == [first, second, first, second]
				assert type(first).version == 2
				assert directory.Handler is type(first)
				handle.cancel()

				key = (id(a), file_path)
				a.Reloadable._records.pop(key)['subscription'].cancel()


if __name__ == '__main__':
	TestReloadable.run()
