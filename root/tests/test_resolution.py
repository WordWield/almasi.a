# ==============================================================================
# TEST RESOLUTION
# ==============================================================================
# Verify on-demand resolution, iteration, and file-carrier ownership.
# ==============================================================================

import os
import shutil
import sys

from unittest.mock import Mock

import almasi


class TestResolution(almasi.Tester):

	# ----------------------------------------------------------------------
	@classmethod
	def _source_root(cls):
		path = os.path.join(almasi.__path__, 'tests_runtime')
		os.makedirs(path, exist_ok=True)
		return path

	# ----------------------------------------------------------------------
	@classmethod
	def _write_source(cls, relative_path, source):
		path = os.path.join(cls._source_root(), relative_path)
		root = os.path.dirname(path)

		os.makedirs(root, exist_ok=True)

		with open(path, 'w') as file:
			file.write(source)

		return path

	# ----------------------------------------------------------------------
	@classmethod
	def _remove_runtime(cls):
		path = os.path.join(almasi.__path__, 'tests_runtime')

		if os.path.isdir(path):
			for module_name in list(sys.modules):
				if module_name.startswith(os.path.realpath(path)):
					del sys.modules[module_name]

			shutil.rmtree(path)

		almasi.__children__.pop('tests_runtime', None)
		almasi.__dict__.pop('tests_runtime', None)
		almasi.__cached_names__.discard('tests_runtime')

	# ----------------------------------------------------------------------
	@classmethod
	def test_attribute_access_is_eager_and_caches_carrier(cls):
		cls._remove_runtime()

		try:
			cls._write_source(
				'eager_carrier.py',
				(
					'import almasi\n\n'
					'class EagerCarrier(almasi.Module):\n'
					'\tvalue = 11\n'
				)
			)
			EagerCarrier = almasi.tests_runtime.EagerCarrier
			directory    = almasi.__children__['tests_runtime']
			carrier      = directory.__children__['EagerCarrier']

			assert EagerCarrier.value == 11
			assert isinstance(directory, almasi.Directory)
			assert isinstance(carrier, almasi.File)
			assert carrier._data is EagerCarrier
		finally:
			cls._remove_runtime()

	# ----------------------------------------------------------------------
	@classmethod
	def test_directory_iteration_is_deferred_discovery(cls):
		cls._remove_runtime()

		try:
			cls._write_source(
				'iter_one.py',
				(
					'import almasi\n\n'
					'class IterOne(almasi.Module):\n'
					'\tvalue = 1\n'
				)
			)
			cls._write_source(
				'iter_two.py',
				(
					'import almasi\n\n'
					'class IterTwo(almasi.Module):\n'
					'\tvalue = 2\n'
				)
			)

			directory = almasi.tests_runtime
			children  = list(directory)
			routes    = sorted(child.get_route() for child in children)

			assert routes == [
				'almasi.tests_runtime.IterOne',
				'almasi.tests_runtime.IterTwo',
			]
			assert all(isinstance(child, almasi.File) for child in children)
			assert all(child._data is None for child in children)
		finally:
			cls._remove_runtime()

	# ----------------------------------------------------------------------
	@classmethod
	def test_file_load_is_memoized(cls):
		load = Mock(return_value={'count': 1})
		file = almasi.File(almasi, __file__, 'almasi.tests.FileMemo', load)
		one  = file.load()
		two  = file.load()

		assert one is two
		assert one == {'count': 1}
		load.assert_called_once_with()

	# ----------------------------------------------------------------------
	@classmethod
	def test_directory_load_returns_self(cls):
		directory = almasi.Directory(almasi, almasi.__path__, 'almasi')

		assert directory.load() is directory
		assert directory.is_directory()

	# ----------------------------------------------------------------------
	@classmethod
	def test_directory_missing_attribute_raises(cls):
		cls._remove_runtime()
		error = None

		try:
			cls._source_root()
			directory = almasi.tests_runtime

			try:
				directory.NoSuchCarrier
			except AttributeError as e:
				error = e

			assert error is not None
			assert 'NoSuchCarrier' in str(error)
		finally:
			cls._remove_runtime()

	# ----------------------------------------------------------------------
	# @classmethod
	# def test_child_directory_falls_back_to_parent_directory(cls):
	# 	cls._remove_runtime()
	# 	child_path = os.path.join(almasi.__path__, 'tests_runtime_child')
	# 	module     = sys.modules[__name__]

	# 	try:
	# 		os.makedirs(os.path.join(child_path, 'tests_runtime', 'parent_dir'), exist_ok=True)
	# 		cls._write_source(
	# 			'parent_dir/parent_thing.py',
	# 			(
	# 				'import almasi\n\n'
	# 				'class ParentThing(almasi.Module):\n'
	# 				'\tvalue = 31\n'
	# 			)
	# 		)

	# 		class ResolutionChild(almasi.A, path=child_path):
	# 			def initialize(self):
	# 				pass

	# 		directory = ResolutionChild.tests_runtime.parent_dir
	# 		thing     = directory.ParentThing

	# 		assert thing.value == 31
	# 		assert directory.get_path() == os.path.realpath(os.path.join(child_path, 'tests_runtime', 'parent_dir'))
	# 		assert thing.__route__ == 'resolutionchild.tests_runtime.parent_dir.ParentThing'
	# 	finally:
	# 		cls._remove_runtime()

	# 		if os.path.isdir(child_path):
	# 			for module_name in list(sys.modules):
	# 				if module_name.startswith(os.path.realpath(child_path)):
	# 					del sys.modules[module_name]

	# 			shutil.rmtree(child_path)

	# 		if 'resolutionchild' in module.__dict__:
	# 			del module.__dict__['resolutionchild']

	# 		if 'resolutionchild' in sys.modules:
	# 			del sys.modules['resolutionchild']


if __name__ == '__main__':
	TestResolution.run()
