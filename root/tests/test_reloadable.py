# ==============================================================================
# TEST RELOADABLE
# ==============================================================================
# Verify automatic source reload and persistent service identity.
# ==============================================================================

import os
import tempfile

from unittest.mock import patch

import almasi


class TestReloadable(almasi.Tester):

	# ==========================================================================
	# PUBLIC METHODS
	# ==========================================================================

	# Source notifications reload services without an external dispatcher.
	# ----------------------------------------------------------------------
	@classmethod
	def test_service_reload(cls):
		with tempfile.TemporaryDirectory(dir=almasi.__path__, prefix='__reloadable_') as path:
			file_path = os.path.join(path, 'counter.py')
			with open(file_path, 'w', encoding='utf-8') as stream:
				stream.write(
					'import almasi\nclass Counter(almasi.ReloadableSingleton):\n'
					'\tdef initialize(self):\n\t\tself.value = 5\n'
					'\tdef read(self):\n\t\treturn self.value + 1\n'
				)

			directory = almasi.Directory(almasi, path, 'almasi.' + os.path.basename(path))
			with patch.object(type(almasi.services.Filesystem), '_watch', return_value=None):
				service = directory.Counter
				service.initialize()
				assert service.read() == 6
				seen         = []
				file         = type(service)._reload_file
				subscription = type(service)._reload_subscription
				type(service).__on_reload__(seen.append)

				with open(file_path, 'w', encoding='utf-8') as stream:
					stream.write(
						'import almasi\nclass Counter(almasi.ReloadableSingleton):\n'
						'\tdef initialize(self):\n\t\traise AssertionError()\n'
						'\tdef read(self):\n\t\treturn self.value + 2\n'
					)
				almasi.services.Filesystem._changed_paths(almasi.__path__, {file_path: 'modified'})
				assert service.read() == 7
				assert directory.Counter is service
				assert type(service)._reload_subscription is subscription
				assert seen == [service]

				with open(file_path, 'w', encoding='utf-8') as stream:
					stream.write(
						'import almasi\nclass Counter(almasi.ReloadableSingleton):\n'
						'\tdef read(self):\n\t\treturn self.value + 3\n'
					)

				almasi.services.Filesystem._changed_paths(almasi.__path__, {file_path: 'modified'})
				assert service.read() == 8
				assert directory.Counter is service
				assert type(service)._reload_subscription is subscription
				assert seen == [service, service]

				assert type(service)._reload_file is file
				file.unsubscribe(subscription)
				assert not file.is_subscribed()
				del type(service).__reload_callback__

	# Report initialized instances and retain class-specific listeners after reload.
	# ----------------------------------------------------------------------
	@classmethod
	def test_module_callbacks(cls):
		with tempfile.TemporaryDirectory(dir=almasi.__path__, prefix='__reloadable_') as path:
			file_path = os.path.join(path, 'handler.py')
			with open(file_path, 'w', encoding='utf-8') as stream:
				stream.write('import almasi\nclass Handler(almasi.ReloadableModule):\n\tpass\n')

			directory = almasi.Directory(almasi, path, 'almasi.' + os.path.basename(path))
			with patch.object(type(almasi.services.Filesystem), '_watch', return_value=None):
				handler = directory.Handler
				seen         = []
				file         = handler._reload_file
				subscription = handler._reload_subscription
				handler.__on_reload__(seen.append)
				first   = handler()
				second  = handler()

				assert seen == [first, second]

				with open(file_path, 'w', encoding='utf-8') as stream:
					stream.write('import almasi\nclass Handler(almasi.ReloadableModule):\n\tversion = 2\n')

				almasi.services.Filesystem._changed_paths(almasi.__path__, {file_path: 'modified'})

				assert seen == [first, second, first, second]
				assert type(first).version == 2
				assert directory.Handler is type(first)
				assert type(first)._reload_subscription is subscription
				del type(first).__reload_callback__

				assert type(first)._reload_file is file
				file.unsubscribe(subscription)
				assert not file.is_subscribed()

	# A subclass inherits one callback, or replaces it with its own.
	# ----------------------------------------------------------------------
	@classmethod
	def test_inherited_callback(cls):
		class Parent(almasi.ReloadableModule):
			pass

		class Child(Parent):
			pass

		class Other(Parent):
			pass

		original = []
		replaced = []

		Parent.__on_reload__(original.append)
		Child()
		assert len(original) == 1

		Parent.__on_reload__(replaced.append)
		Child()
		assert len(original) == 1
		assert len(replaced) == 1

		Child.__on_reload__(original.append)
		Child()
		Other()
		assert len(original) == 2
		assert len(replaced) == 2



if __name__ == '__main__':
	TestReloadable.run()
