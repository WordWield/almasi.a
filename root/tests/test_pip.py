# ==============================================================================
# TEST PIP
# ==============================================================================
# PURPOSE:
# Verify requirements synchronization, package commands and declaration edits.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Isolated fixtures and assertions.
# Delegates: File mutation to the real Directory and execution to mocked pip.
# ==============================================================================

import os
import subprocess
import sys
import tempfile

from unittest      import TestCase
from unittest.mock import patch

from almasi import a


class TestPip(a.Tester):

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Exercise the actual service contract without altering the test environment.
	# ----------------------------------------------------------------------
	@classmethod
	def test_requirements(cls):
		class Fixture(a.services.Pip):
			pass

		pip = Fixture()

		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, 'requirements.txt')

			with patch('subprocess.run') as run:
				run.return_value = subprocess.CompletedProcess([], 0, '', '')
				pip.initialize(path)
				assert os.path.isfile(path)
				run.assert_not_called()

				with open(path, 'w', encoding='utf-8') as stream:
					stream.write('# Direct dependencies\nother>=1\nmy-package-extra>=1\nMy_Package==1\nmy-package >= 1\nmy-package\n')

				pip.sync()
				assert run.call_args.args[0][-3:] == ['install', '-r', path]
				assert run.call_args.args[0][:3] == [sys.executable, '-m', 'pip']

				pip.install('my-package', min_version='2', max_version='3')
				assert run.call_args.args[0][-2:] == ['install', 'my-package>=2,<=3']

				with open(path, encoding='utf-8') as stream:
					assert stream.read() == '# Direct dependencies\nother>=1\nmy-package-extra>=1\nmy-package>=2,<=3\n'

				pip.uninstall('MY_PACKAGE')
				assert run.call_args.args[0][-3:] == ['uninstall', '-y', 'my-package']

				with open(path, encoding='utf-8') as stream:
					assert stream.read() == '# Direct dependencies\nother>=1\nmy-package-extra>=1\n'

				run.return_value = subprocess.CompletedProcess([], 0, '[{"name":"other","version":"1.2"}]', '')
				assert pip.list() == {'other': '1.2'}
				run.return_value = subprocess.CompletedProcess([], 0, 'other==1.2\n', '')
				assert pip.freeze() == 'other==1.2\n'

				with open(path, encoding='utf-8') as stream:
					assert stream.read() == '# Direct dependencies\nother>=1\nmy-package-extra>=1\n'

				run.side_effect = subprocess.CalledProcessError(1, ['pip'], stderr='Failed')

				for method, arguments in ((pip.install, ('missing',)), (pip.uninstall, ('other',))):
					with TestCase().assertRaises(subprocess.CalledProcessError):
						method(*arguments)

					with open(path, encoding='utf-8') as stream:
						assert stream.read() == '# Direct dependencies\nother>=1\nmy-package-extra>=1\n'

				run.reset_mock()
				with TestCase().assertRaises(ValueError):
					pip.install('--index-url')
				with TestCase().assertRaises(ValueError):
					pip.install('other', min_version='3', max_version='2')
				run.assert_not_called()

	# Initialize a present file and leave its original declaration intact.
	# ----------------------------------------------------------------------
	@classmethod
	def test_existing_requirements(cls):
		class Fixture(a.services.Pip):
			pass

		pip = Fixture()

		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, 'requirements.txt')

			with open(path, 'w', encoding='utf-8') as stream:
				stream.write('example>=1\n')

			with patch('subprocess.run') as run:
				run.return_value = subprocess.CompletedProcess([], 0, '', '')
				pip.initialize(path)
				assert run.call_args.args[0][-3:] == ['install', '-r', path]

				with patch.object(a.__PLUGINS__['Text'], 'write', side_effect=OSError('Write failed')):
					with TestCase().assertRaises(OSError):
						pip.install('example', min_version='2')

				with open(path, encoding='utf-8') as stream:
					assert stream.read() == 'example>=1\n'

				assert os.listdir(directory) == ['requirements.txt']
