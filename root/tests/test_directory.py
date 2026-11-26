# ==============================================================================
# TEST DIRECTORY
# ==============================================================================
# Verify native filesystem operations and resolved namespace behavior.
# ==============================================================================

import json
import os
import tempfile
import uuid

from unittest import TestCase
from unittest.mock import patch

from almasi import a


class TestDirectory(a.Tester):

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Create and resolve children in an explicitly supplied external directory.
	# ----------------------------------------------------------------------
	@classmethod
	def test_external_directory(cls):
		with tempfile.TemporaryDirectory() as path:
			directory = a.Directory(a, path, 'almasi.output')
			workspace = directory.mkdir('lesson', 'workspace')

			workspace.write('scenario.json', {'title': 'External output'})

			assert workspace.get_path() == os.path.realpath(os.path.join(path, 'lesson', 'workspace'))
			assert directory.lesson.workspace.scenario == {'title': 'External output'}

	# Import class-free Python definitions with or without the extension.
	# ----------------------------------------------------------------------
	@classmethod
	def test_import_python(cls):
		with tempfile.TemporaryDirectory(dir=a.__path__, prefix='__import_') as path:
			directory = a.Directory(a, path, 'almasi.import_test')
			filename  = os.path.join(path, 'definitions.py')

			with open(filename, 'w') as source:
				source.write('VALUE = 23\n')

			module = directory.import_python('definitions')

			assert module.VALUE == 23
			assert module.__route__ == 'almasi.import_test.definitions'
			assert module.__lib__ is a
			assert directory.import_python('definitions.py') is module

	# Import Python files recursively, preserving native class loading.
	# ----------------------------------------------------------------------
	@classmethod
	def test_import_python_recursive(cls):
		with tempfile.TemporaryDirectory(dir=a.__path__, prefix='__import_') as path:
			directory = a.Directory(a, path, 'almasi.import_test')
			nested    = os.path.join(path, 'nested')
			os.mkdir(nested)

			with open(os.path.join(path, 'definitions.py'), 'w') as source:
				source.write('VALUE = 23\n')

			with open(os.path.join(nested, 'example.py'), 'w') as source:
				source.write('from almasi import a\nclass Example(a.Module):\n\tpass\n')

			modules = directory.import_python(None)

			assert len(modules) == 2
			assert next(module for module in modules if hasattr(module, 'VALUE')).VALUE == 23

			example = next(module.Example for module in modules if hasattr(module, 'Example'))

			assert example.__has_own_module__
			assert example.__route__ == 'almasi.import_test.nested.Example'
			assert directory.import_python(None) == modules

	# Preserve missing-file errors and class-name resolution semantics.
	# ----------------------------------------------------------------------
	@classmethod
	def test_import_python_errors(cls):
		with tempfile.TemporaryDirectory(dir=a.__path__, prefix='__import_') as path:
			directory = a.Directory(a, path, 'almasi.import_test')

			with TestCase().assertRaises(FileNotFoundError):
				directory.import_python('missing')

			with TestCase().assertRaises(ValueError):
				directory.import_python('../escape.py')

			filename = os.path.join(path, 'definitions.py')
			with open(filename, 'w') as source:
				source.write('VALUE = 23\n')

			with TestCase().assertRaises(AttributeError):
				directory.Definitions

	# Round-trip supported text formats through the native namespace.
	# ----------------------------------------------------------------------
	@classmethod
	def test_write_text(cls):
		with tempfile.TemporaryDirectory(dir=a.__path__, prefix='__write_') as path:
			directory = a.Directory(a, path, 'almasi.write_test')

			for name, value in (('intro.md', '# Привет 🐍\n'), ('notes.txt', 'Hello, world!')):
				directory.write(name, value)

				assert getattr(directory, os.path.splitext(name)[0]) == value
				with open(os.path.join(path, name), encoding='utf-8') as file:
					assert file.read() == value

	# Preserve JSON data and readable UTF-8 formatting.
	# ----------------------------------------------------------------------
	@classmethod
	def test_write_json(cls):
		with tempfile.TemporaryDirectory(dir=a.__path__, prefix='__write_') as path:
			directory = a.Directory(a, path, 'almasi.write_test')
			value     = {'title': 'Урок 🐍', 'scenes': [], 'active': True}

			directory.write('scenario.json', value)

			assert directory.scenario == value
			with open(os.path.join(path, 'scenario.json'), encoding='utf-8') as file:
				assert file.read() == json.dumps(value, indent=2, ensure_ascii=False) + '\n'

	# Resolve a replacement carrier after writing through the same directory.
	# ----------------------------------------------------------------------
	@classmethod
	def test_write_refreshes_own_children(cls):
		with tempfile.TemporaryDirectory(dir=a.__path__, prefix='__write_') as path:
			directory = a.Directory(a, path, 'almasi.write_test')

			for name, before, after in (
				('notes.txt', 'before', 'after'),
				('scenario.json', {'value': 1}, {'value': 2}),
			):
				stem = os.path.splitext(name)[0]

				directory.write(name, before)
				assert getattr(directory, stem) == before

				directory.write(name, after)
				assert getattr(directory, stem) == after

	# Keep the resolver's existing extension priority when stems coincide.
	# ----------------------------------------------------------------------
	@classmethod
	def test_write_preserves_extension_priority(cls):
		with tempfile.TemporaryDirectory(dir=a.__path__, prefix='__write_') as path:
			directory = a.Directory(a, path, 'almasi.write_test')

			directory.write('notes.md', 'markdown')
			assert directory.notes == 'markdown'

			directory.write('notes.txt', 'text')
			assert directory.notes == 'text'

			directory.write('notes.md', 'updated markdown')
			assert directory.notes == 'text'
			with open(os.path.join(path, 'notes.md'), encoding='utf-8') as file:
				assert file.read() == 'updated markdown'

	# Reject invalid names and formats before creating a file.
	# ----------------------------------------------------------------------
	@classmethod
	def test_write_rejects_invalid_names(cls):
		with tempfile.TemporaryDirectory(dir=a.__path__, prefix='__write_') as path:
			directory = a.Directory(a, path, 'almasi.write_test')

			for name in ('', '.', '..', '../escape.txt', '/absolute.txt', 'nested/file.txt', None, 42):
				with TestCase().assertRaises(ValueError):
					directory.write(name, 'text')

			for name in ('notes', 'notes.yaml'):
				with TestCase().assertRaises(ValueError):
					directory.write(name, 'text')

			assert os.listdir(path) == []

	# Reject a non-string before opening an existing text file for writing.
	# ----------------------------------------------------------------------
	@classmethod
	def test_write_rejects_non_text(cls):
		with tempfile.TemporaryDirectory(dir=a.__path__, prefix='__write_') as path:
			directory = a.Directory(a, path, 'almasi.write_test')

			directory.write('notes.txt', 'original')

			with TestCase().assertRaises(TypeError):
				directory.write('notes.txt', {'value': 1})

			assert directory.notes == 'original'
			with open(os.path.join(path, 'notes.txt'), encoding='utf-8') as file:
				assert file.read() == 'original'

	# Refuse both live and dangling symbolic-link destinations.
	# ----------------------------------------------------------------------
	@classmethod
	def test_write_rejects_symbolic_links(cls):
		with tempfile.TemporaryDirectory(dir=a.__path__, prefix='__write_') as path:
			directory = a.Directory(a, path, 'almasi.write_test')
			target    = os.path.join(path, 'target.txt')

			directory.write('target.txt', 'original')
			os.symlink(target, os.path.join(path, 'notes.txt'))
			os.symlink(os.path.join(path, 'missing.txt'), os.path.join(path, 'missing_link.txt'))

			for name in ('notes.txt', 'missing_link.txt'):
				with TestCase().assertRaises(ValueError):
					directory.write(name, 'replacement')

			with open(target, encoding='utf-8') as file:
				assert file.read() == 'original'
			assert not os.path.exists(os.path.join(path, 'missing.txt'))

	# Use the owning plugin's serializer without bypassing library lineage.
	# ----------------------------------------------------------------------
	@classmethod
	def test_write_delegates_to_plugin(cls):
		with tempfile.TemporaryDirectory(dir=a.__path__, prefix='__write_') as path:
			directory = a.Directory(a, path, 'almasi.write_test')
			plugin    = a.__PLUGINS__['Text']

			with patch.object(plugin, 'write', wraps=plugin.write) as write:
				directory.write('notes.txt', 'text')

				write.assert_called_once_with(directory.join('notes.txt'), value='text')

	# Delegate root writes and replace the library's cached child carrier.
	# ----------------------------------------------------------------------
	@classmethod
	def test_library_write(cls):
		name = '__write_' + uuid.uuid4().hex
		path = os.path.join(a.__path__, name + '.json')

		try:
			a.write(name + '.json', {'value': 1})
			assert getattr(a, name) == {'value': 1}

			a.write(name + '.json', {'value': 2})
			assert getattr(a, name) == {'value': 2}
		finally:
			if os.path.isfile(path):
				os.unlink(path)
			a.__children__.pop(name, None)
			a.__dict__.pop(name, None)
			a.__cached_names__.discard(name)


if __name__ == '__main__':
	TestDirectory.run()
