import asyncio
import time

from unittest.mock import patch

import almasi
from lib.events import Events
from lib.function import Function


class TestCore(almasi.Tester):

	# ----------------------------------------------------------------------
	@classmethod
	def test_undefined_surface(cls):
		error    = None
		expected = f'{almasi.Undefined.__lib__.__name__}.Undefined'

		assert bool(almasi.Undefined) == False
		assert repr(almasi.Undefined) == expected
		assert str(almasi.Undefined) == expected

		try:
			almasi.Undefined.foo
		except AttributeError as e:
			error = e

		assert error is not None
		assert str(error) == '`Undefined` has no attribute `foo`'

	# ----------------------------------------------------------------------
	@classmethod
	def test_undefined_rejects_use_as_value(cls):
		errors = []

		for action in [
			lambda: almasi.Undefined(),
			lambda: almasi.Undefined['x'],
			lambda: len(almasi.Undefined),
			lambda: iter(almasi.Undefined),
		]:
			try:
				action()
			except TypeError as e:
				errors.append(str(e))

		assert errors == [
			'`Undefined` is not callable',
			'`Undefined` is not subscriptable',
			'`Undefined` has no len()',
			'`Undefined` is not iterable',
		]

	# ----------------------------------------------------------------------
	@classmethod
	def test_string_naming_conversions(cls):
		assert almasi.String.snake_to_camel('almasi') == 'Almasi'
		assert almasi.String.snake_to_camel('almasi', capitalize=False) == 'almasi'
		assert almasi.String.camel_to_snake('Almasi') == 'almasi'
		assert almasi.String.camel_to_snake('VectorDB') == 'vector_d_b'
		assert almasi.String.camel_to_snake('VectorDB', allow_consequent_caps=True) == 'vector_db'
		assert almasi.String.normalize_whitespace('  one\n\t two   ') == 'one two'

	# ----------------------------------------------------------------------
	@classmethod
	def test_string_formatting(cls):
		assert almasi.String.indent('a\n\nb', prefix='> ') == '> a\n\n> b'
		assert almasi.String.underlined('x') == f'{almasi.String.UNDERLINE}x{almasi.String.RESET}'
		assert almasi.String.italic('x') == f'{almasi.String.ITALIC}x{almasi.String.RESET}'
		assert almasi.String.strikethrough('x') == f'{almasi.String.STRIKETHROUGH}x{almasi.String.RESET}'
		assert almasi.String.color('x') == 'x'
		assert almasi.String.color('x', almasi.String.RED, 'bu') == (
			f'{almasi.String.BOLD}{almasi.String.UNDERLINE}{almasi.String.RED}x{almasi.String.RESET}'
		)

	# ----------------------------------------------------------------------
	@classmethod
	def test_string_hash_shape(cls):
		one = almasi.String.hash('almasi', digits=12)
		two = almasi.String.hash('almasi', digits=12)

		assert one == two
		assert isinstance(one, int)
		assert len(str(one)) == 12

	# ----------------------------------------------------------------------
	@classmethod
	def test_function_identity_and_call(cls):
		def init(self):
			self.value = 3

		def instance(self, x):
			return self.value + x

		def klass(cls, x):
			return x + 4

		def static(x):
			return x + 5

		Example = type(
			'Example',
			(),
			{
				'__init__' : init,
				'instance' : instance,
				'klass'    : classmethod(klass),
				'static'   : staticmethod(static),
			}
		)

		example      = Example()
		instance_one = Function(example.instance)
		instance_two = Function(example.instance)
		klass        = Function(Example.klass)
		static       = Function(Example.static)

		assert instance_one == instance_two
		assert hash(instance_one) == hash(instance_two)
		assert instance_one(4) == 7
		assert klass(4) == 8
		assert static(4) == 9
		assert Function(instance_one) == instance_one

	# ----------------------------------------------------------------------
	@classmethod
	def test_function_async_call(cls):
		async def run(x):
			return x + 1

		result = asyncio.run(Function(run)(4))

		assert result == 5
		assert Function(run).is_async() == True

	# Account for recursively nested calls sharing a timer name.
	# ----------------------------------------------------------------------
	@classmethod
	def test_timer_nested_same_name(cls):
		almasi.Timer.reset()

		with patch('lib.timer.time.perf_counter', side_effect=[1.0, 2.0, 3.0, 4.0]):
			almasi.Timer.start('nested')
			almasi.Timer.start('nested')
			almasi.Timer.stop('nested')
			almasi.Timer.stop('nested')

		assert almasi.Timer._times['nested'] == [1.0, 3.0]
		assert almasi.Timer._start['nested'] == []

		almasi.Timer.reset()

	# Accumulate distinct intervals and reset measurements.
	# ----------------------------------------------------------------------
	@classmethod
	def test_timer_accumulates_and_resets(cls):
		almasi.Timer.reset()
		almasi.Timer.start('almasi-test')
		time.sleep(0.001)
		almasi.Timer.stop('almasi-test')

		assert almasi.Timer.get_time('almasi-test') > 0

		almasi.Timer.reset()

		assert almasi.Timer.get_time('almasi-test') == 0


if __name__ == '__main__':
	TestCore.run()
