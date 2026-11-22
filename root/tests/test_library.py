import os
import sys

import almasi


class TestLibrary(almasi.Tester):

	# ----------------------------------------------------------------------
	@classmethod
	def test_published_face_is_canonical_instance(cls):
		import almasi as imported

		assert imported is almasi
		assert sys.modules['almasi'] is almasi
		assert type(almasi).__name__ == 'A'
		assert type(almasi).__instance__ is almasi
		assert almasi.A is type(almasi)

	# ----------------------------------------------------------------------
	@classmethod
	def test_library_paths_are_separate(cls):
		lib_path  = os.path.dirname(os.path.realpath(almasi.__lib_file__))
		root_path = os.path.join(lib_path, 'root')

		assert os.path.realpath(almasi.__path__) == root_path
		assert os.path.realpath(almasi.__lib_path__) == lib_path
		assert os.path.basename(almasi.__lib_file__) == 'almasi.py'
		assert almasi.__path__ != almasi.__lib_path__

	# ----------------------------------------------------------------------
	@classmethod
	def test_kernel_names_are_intrinsic(cls):
		assert almasi.Module is almasi.A.Module
		assert almasi.ModuleMeta is almasi.A.ModuleMeta
		assert almasi.File is almasi.A.File
		assert almasi.Directory is almasi.A.Directory
		assert almasi.Plugin is almasi.A.Plugin
		assert almasi.Singleton is almasi.A.Singleton
		assert almasi.Imports is almasi.A.Imports
		assert almasi.Undefined is almasi.A.Undefined
		assert almasi.String is almasi.A.String
		assert almasi.Timer is almasi.A.Timer
		assert almasi.Tester is almasi.A.Tester
		assert almasi.tester is almasi.Tester

	# ----------------------------------------------------------------------
	@classmethod
	def test_shared_lib_contract_points_to_instance(cls):
		instance = almasi.Tester.__lib__

		assert almasi.Imports.__lib__ is instance
		assert almasi.Tester.__lib__ is instance
		assert almasi.Undefined.__lib__ is instance
		assert instance in list(instance.__instances__())

	# ----------------------------------------------------------------------
	@classmethod
	def test_instances_iterate_lineage_heads(cls):
		instances = list(almasi.__instances__())

		assert instances == [almasi]
		assert instances[0].__name__ == 'almasi'
		assert instances[0].__spec__ is None
		assert isinstance(instances[0].__children__, dict)

	# ----------------------------------------------------------------------
	@classmethod
	def test_repr_and_missing_attribute(cls):
		error = None

		assert repr(almasi) == '<Library `almasi`>'

		try:
			almasi.NoSuchAlmasiThing
		except AttributeError as e:
			error = e

		assert error is not None
		assert str(error) == 'Library `almasi` has no attribute `NoSuchAlmasiThing`'



if __name__ == '__main__':
	TestLibrary.run()
