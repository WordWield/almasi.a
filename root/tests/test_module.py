import asyncio
import inspect
import os
import shutil
import sys
import typing as t

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

			def named(owner, method: str, self: str) -> str:
				return method + self

			def wrong(self) -> int:
				return 'wrong'

		example = Example()
		method  = Example.call

		assert example.call(2) == 3
		assert example.bind('untyped') == 'untyped'
		assert example.__call_method__(example.call, 3, offset=4) == 7
		assert asyncio.run(example.__call_method__(example.read, [1, None])) == {'count': 2}
		assert example.__call_method__(example.named, method='a', self='b') == 'ab'
		assert Example.call is method
		assert inspect.signature(example.call) == example.__get_method_signature__(example.call)
		assert example.calls == 2

		for target, arguments in (
			(example.call, ('3',)),
			(example.read, (['3'],)),
			(example.bind, ('untyped',)),
			(example.wrong, ())
		):
			try:
				example.__call_method__(target, *arguments)
			except TypeError:
				pass
			else:
				assert False, 'Invalid typed call accepted'

		assert example.calls == 2
		assert example.bind(9) == 9


	# Reflection is independent of typing and never executes a property.
	# ----------------------------------------------------------------------
	@classmethod
	def test_method_reflection(cls):
		class Parent(a.Module):

			def first(self, value):
				return value

			first.exposed = True

			@property
			def dangerous(self):
				raise RuntimeError('Discovery evaluated a property')

			@classmethod
			def third(cls):
				return cls

			@staticmethod
			def fourth(value):
				return value

		class Child(Parent):

			def first(self, value):
				return value + 1

			def second(self, value: int) -> int:
				return value

			second.exposed = True

		child = Child()

		assert child.__get_method__('first')(1) == 2
		assert child.__get_method__('first', exposed=True) is None
		assert child.__get_method__('second', exposed=True) == child.second
		assert child.__get_method__('dangerous') is None
		assert child.__get_method__('__get_method__') is None
		assert child.__get_method__('third')() is Child
		assert child.__get_method__('fourth')(3) == 3
		assert list(child.__list_methods__(exposed=True)) == [child.second]
		assert child.__get_method_signature__(child.first).return_annotation is inspect.Signature.empty


	# Matching must preserve actual types instead of coercing values.
	# ----------------------------------------------------------------------
	@classmethod
	def test_annotation_matches(cls):
		for declaration, value, expected in (
			(int, 3, True),
			(int, '3', False),
			(t.Any, object(), True),
			(int | None, None, True),
			(list[int | None], [1, None], True),
			(list[int], ['1'], False),
			(dict[str, list[int]], {'a': [1, 2]}, True),
			(dict[str, int], {1: 2}, False),
			(set[int], {1, 2}, True),
			(frozenset[int], frozenset({'1'}), False),
			(tuple[int, str], (1, 'a'), True),
			(tuple[int, ...], (1, 2), True),
			(tuple[int, ...], (1, '2'), False),
			(t.Tuple, (1, 'a'), True),
			(tuple[()], (), True),
			(tuple[()], (1,), False),
			(t.Literal[1], True, False),
			(t.Literal['one', 'two'], 'one', True),
			(t.Annotated[int, 'metadata'], 1, True),
			(a.Resource[int], a.resources.Writable(1), True),
		):
			assert a.Annotation(declaration).matches(value) is expected, declaration

		assert a.Annotation(int).cast('3') == 3
		assert not a.Annotation(int).matches('3')
		assert a.Annotation(dict[str, list[int]]).cast({'a': ['1']}) == {'a': [1]}

	# Core source expressions round-trip without importing O.
	# ----------------------------------------------------------------------
	@classmethod
	def test_annotation_source(cls):
		for declaration in (int, t.Any, list[int], dict[str, int | None], tuple[int, ...], tuple[()], t.Literal['x'], t.Annotated[int, 'tag']):
			annotation = a.Annotation(declaration)
			restored   = a.Annotation(annotation.to_source())

			assert restored.annotation == annotation.annotation
			assert restored.id == annotation.id
			assert hash(restored) == hash(annotation)


if __name__ == '__main__':
	TestModule.run()
