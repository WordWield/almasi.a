# ======================================================================
# Exercise scoped logging independently of applications and ontology.
# ======================================================================

import asyncio
import contextvars
import logging
import tempfile
import threading

from concurrent.futures import ThreadPoolExecutor
from unittest.mock      import patch

import almasi


class TestLogger(almasi.Tester):

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Interleave independent logging scopes across asynchronous tasks.
	# ----------------------------------------------------------------------
	@staticmethod
	async def _concurrent(directory):
		async def emit(name):
			with almasi.Logger().logging(directory.mkdir(name)):
				logging.info('%s before', name)
				await asyncio.sleep(0)
				logging.warning('%s after', name)

		await asyncio.gather(emit('alpha'), emit('beta'))

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Verify routing, serialization, numbering, append behavior and cleanup.
	# ----------------------------------------------------------------------
	@classmethod
	def test_scopes_and_artifacts(cls):
		root     = logging.getLogger()
		handlers = tuple(root.handlers)
		level    = root.level
		with tempfile.TemporaryDirectory() as path:
			directory = almasi.Directory(almasi, path, 'logger_test')
			logger    = almasi.Logger()
			with logger.logging(directory):
				logging.getLogger('third_party').info('outer message')
				logging.debug('ignored debug')
				with almasi.Logger().logging(almasi.Directory(almasi, directory.join('nested'), 'reopened')):
					logging.info('nested message')
					logging.info('input', extra={
						'artifact_name' : 'input_Storyteller.txt',
						'artifact_data' : 'private prompt',
					})
					logging.info('output', extra={
						'artifact_name' : 'output_Storyteller.json',
						'artifact_data' : {'answer': 42},
					})
				logging.info('restored directory')
				logging.info('direct model input', extra={
					'artifact_name' : 'input_vendor/model.txt',
					'artifact_data' : 'direct prompt',
				})

			with almasi.Logger().logging(almasi.Directory(almasi, directory.join('nested'), 'reopened')):
				logging.info('input', extra={
					'artifact_name' : 'input_Storyteller.txt',
					'artifact_data' : 'another prompt',
				})

			outer  = directory.read('log.txt')
			nested = directory.nested.read('log.txt')
			assert outer.count('nested message') == 1
			assert directory.read('input_vendor_model_001.txt') == 'direct prompt'
			assert 'outer message' not in nested
			assert 'restored directory' in outer and 'restored directory' not in nested
			assert 'private prompt' not in outer + nested
			assert 'ignored debug' not in outer + nested
			assert directory.nested.read('input_Storyteller_001.txt') == 'private prompt'
			assert directory.nested.read('input_Storyteller_002.txt') == 'another prompt'
			assert directory.nested.read('output_Storyteller_001.json') == {'answer': 42}
			assert 'input_Storyteller_001.txt' in nested

		try:
			with tempfile.TemporaryDirectory() as path:
				with almasi.Logger().logging(almasi.Directory(almasi, path, 'failure')):
					int('expected failure')
		except ValueError:
			pass
		assert tuple(root.handlers) == handlers and root.level == level

	# Prove that task-local directories do not mix events.
	# ----------------------------------------------------------------------
	@classmethod
	def test_concurrent_isolation(cls):
		with tempfile.TemporaryDirectory() as path:
			directory = almasi.Directory(almasi, path, 'logger_concurrent')
			asyncio.run(cls._concurrent(directory))
			assert 'beta' not in directory.alpha.read('log.txt')
			assert 'alpha' not in directory.beta.read('log.txt')

	# Preserve external logger changes and surface required artifact failures.
	# ----------------------------------------------------------------------
	@classmethod
	def test_logging_policy(cls):
		root      = logging.getLogger()
		original  = root.level
		third     = logging.getLogger('logger_policy')
		old_level = third.level
		third.setLevel(logging.WARNING)
		try:
			with tempfile.TemporaryDirectory() as path:
				directory = almasi.Directory(almasi, path, 'policy')
				with almasi.Logger().logging(directory):
					assert third.level == logging.WARNING
					root.setLevel(logging.ERROR)
					third.setLevel(logging.ERROR)
				assert root.level == logging.ERROR and third.level == logging.ERROR

			with tempfile.TemporaryDirectory() as path:
				directory = almasi.Directory(almasi, path, 'artifact_failure')
				with almasi.Logger().logging(directory), patch.object(almasi.Logger, '_artifact', side_effect=OSError('disk full')):
					try:
						logging.warning('artifact', extra={'artifact_name': 'input.txt', 'artifact_data': 'text'})
					except OSError:
						pass
					else:
						raise AssertionError('Artifact failure was swallowed')
		finally:
			root.setLevel(original)
			third.setLevel(old_level)

	# Respect a named logger's threshold before routing eligible records.
	# ----------------------------------------------------------------------
	@classmethod
	def test_named_logger_level(cls):
		logger = logging.getLogger('logger_level_contract')
		level  = logger.level
		try:
			with tempfile.TemporaryDirectory() as path:
				directory = almasi.Directory(almasi, path, 'level_contract')
				logger.setLevel(logging.WARNING)
				with almasi.Logger().logging(directory):
					logger.info('suppressed')
					logger.warning('visible warning')
					logger.setLevel(logging.INFO)
					logger.info('visible info')
				content = directory.read('log.txt')
				assert 'suppressed' not in content
				assert 'visible warning' in content and 'visible info' in content
		finally:
			logger.setLevel(level)

	# Concurrent threads must reserve and write distinct artifact numbers.
	# ----------------------------------------------------------------------
	@classmethod
	def test_threaded_artifact_numbering(cls):
		with tempfile.TemporaryDirectory() as path:
			directory = almasi.Directory(almasi, path, 'threaded_artifacts')
			barrier   = threading.Barrier(8)

			def emit(index):
				barrier.wait(timeout=10)
				logging.info('input', extra={
					'artifact_name' : 'input_Thread.txt',
					'artifact_data' : str(index),
				})

			with almasi.Logger().logging(directory), ThreadPoolExecutor(max_workers=8) as pool:
				futures = [pool.submit(contextvars.copy_context().run, emit, index) for index in range(8)]
				for future in futures:
					future.result(timeout=10)

			filenames = sorted(child.get_name() for child in directory if child.get_name().startswith('input_Thread_'))
			assert filenames == [f'input_Thread_{index:03d}.txt' for index in range(1, 9)]
			assert {directory.read(name) for name in filenames} == {str(index) for index in range(8)}
