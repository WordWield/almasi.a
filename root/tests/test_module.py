import asyncio
import inspect
import os
import shutil
import sys

from almasi import a


class TestModule(a.Tester):

	# ----------------------------------------------------------------------
	@classmethod
	def _source_root(cls):
		path = os.path.join(a.__path__, 'tests_runtime')
		os.makedirs(path, exist_ok=True)
		return path

	# ----------------------------------------------------------------------
	@classmethod
	def _source_path(cls, file_name):
		return os.path.join(cls._source_root(), file_name)

	# ----------------------------------------------------------------------
	@classmethod
	def _write_source(cls, file_name, source):
		path = cls._source_path(file_name)

		with open(path, 'w') as file:
			file.write(source)

		return path

	# ----------------------------------------------------------------------
	@classmethod
	def _remove_runtime(cls):
		path = os.path.join(a.__path__, 'tests_runtime')

		if os.path.isdir(path):
			for module_name in list(sys.modules):
				if module_name.startswith(os.path.realpath(path)):
					del sys.modules[module_name]

			shutil.rmtree(path)

		a.__children__.pop('tests_runtime', None)
		a.__dict__.pop('tests_runtime', None)
		a.__cached_names__.discard('tests_runtime')

	# ----------------------------------------------------------------------
	@classmethod
	def test_source_carrier_gets_route_lib_and_own_module(cls):
		cls._remove_runtime()

		try:
			path = cls._write_source(
				'source_carrier.py',
				(
					'from almasi import a\n\n'
					'class SourceCarrier(a.Module):\n'
					'\tvalue = 7\n'
				)
			)
			SourceCarrier = a.tests_runtime.SourceCarrier
			module        = sys.modules[os.path.realpath(path)]

			assert module.__lib__ is a
			assert module.__route__ == 'almasi.a.tests_runtime.SourceCarrier'
			assert SourceCarrier.__route__ == 'almasi.a.tests_runtime.SourceCarrier'
			assert SourceCarrier.__has_own_module__ == True
			assert '__original_module__' not in SourceCarrier.__dict__
			assert SourceCarrier.value == 7
			assert repr(SourceCarrier) == '<class \'almasi.a.tests_runtime.SourceCarrier\'>'
		finally:
			cls._remove_runtime()

	# ----------------------------------------------------------------------
	@classmethod
	def test_file_name_to_class_name_law_is_enforced(cls):
		cls._remove_runtime()
		error = None

		try:
			cls._write_source(
				'wrong_name.py',
				(
					'from almasi import a\n\n'
					'class NotWrongName(a.Module):\n'
					'\tpass\n'
				)
			)

			try:
				a.tests_runtime.WrongName
			except AttributeError as e:
				error = e

			assert error is not None
			assert 'WrongName' in str(error)
		finally:
			cls._remove_runtime()

	# ----------------------------------------------------------------------
	@classmethod
	def test_module_law_is_enforced(cls):
		cls._remove_runtime()
		error = None

		try:
			cls._write_source(
				'plain_carrier.py',
				(
					'class PlainCarrier:\n'
					'\tpass\n'
				)
			)

			try:
				a.tests_runtime.PlainCarrier
			except Exception as e:
				error = e

			assert error is not None
			assert 'does not extend from `Module`' in str(error)
		finally:
			cls._remove_runtime()

	# ----------------------------------------------------------------------
	@classmethod
	def test_runtime_class_without_route_is_not_own_module(cls):
		RuntimeOnly = type('RuntimeOnly', (a.Module,), {'value' : 1})

		assert RuntimeOnly.__has_own_module__ == False
		assert '__route__' not in RuntimeOnly.__dict__
		assert repr(RuntimeOnly) == '<class \'RuntimeOnly\'>'
		assert repr(RuntimeOnly()) == '<Module \'RuntimeOnly\'>'
		assert RuntimeOnly.value == 1


	# Strict is opt-in and leaves existing methods and lifecycle unchanged.
	# ----------------------------------------------------------------------
	@classmethod
	def test_strict_mixin(cls):
		class Example(a.base.Strict):

			def __init__(self):
				self.calls = 0

			def call(self, value: int, offset: int = 1) -> int:
				self.calls += 1
				return value + offset

			def bind(self, value):
				return value

			async def read(self, values: list[int | None]) -> dict[str, int]:
				return {'count': len(values)}

			def wrong(self) -> int:
				return 'wrong'

		example = Example()
		method  = Example.call

		assert example.call(2) == 3
		assert example.bind('untyped') == 'untyped'
		assert example.strict_call(example.call, 3, offset=4) == 7
		assert asyncio.run(example.strict_call(example.read, [1, None])) == {'count': 2}
		assert Example.call is method
		assert inspect.signature(example.call) == example.strict_signature(example.call)
		assert example.calls == 2

		for target, arguments in (
			(example.call, ('3',)),
			(example.read, (['3'],)),
			(example.bind, ('untyped',)),
			(example.wrong, ())
		):
			try:
				example.strict_call(target, *arguments)
			except TypeError:
				pass
			else:
				assert False, 'Invalid typed call accepted'

		assert example.calls == 2
		assert example.bind(9) == 9


if __name__ == '__main__':
	TestModule.run()
