# ==============================================================================
# TEST RESOURCE SUBSCRIPTIONS
# ==============================================================================
# PURPOSE:
# Verify resource subscriptions and effective filesystem invalidations.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Assertions about registration, cancellation and watcher lifetimes.
# Delegates: Observation and dispatch to the real resource implementations.
# ==============================================================================

import asyncio
import os
import shutil
import tempfile
import threading
import time
import uuid

from unittest.mock import Mock, patch

from watchfiles import Change

from almasi import a


class TestResourceSubscriptions(a.Tester):

	# ==========================================================================
	# PUBLIC METHODS
	# ==========================================================================

	# Split common resource identity without losing the established file API.
	# --------------------------------------------------------------------------
	@classmethod
	def test_resource_hierarchy(cls):
		assert issubclass(a.File, a.FilesystemResource)
		assert issubclass(a.Directory, a.FilesystemResource)
		assert issubclass(a.FilesystemResource, a.Resource)
		assert issubclass(a.Resource, a.Module)
		assert issubclass(a.File, a.Module)
		assert issubclass(a.Directory, a.Module)
		assert a.Resource.__bases__ == (a.Module,)
		assert not issubclass(a.Directory, a.File)
		assert a.File.is_directory(a.File(a, __file__, 'almasi.file')) is False
		assert a.Directory(a, os.path.dirname(__file__), 'almasi.tests').is_directory() is True
		assert a.File.subscribe is a.Resource.subscribe
		assert a.Directory.subscribe is a.Resource.subscribe
		assert not hasattr(a.Directory, 'load')
		assert a.File.read is not a.Resource.read
		assert a.Directory.read is not a.Resource.read

	# Base resources have no dependency on filesystem APIs or runtime services.
	# --------------------------------------------------------------------------
	@classmethod
	def test_generic_resource_contract(cls):
		resource = a.Resource()

		try:
			resource.read()
		except NotImplementedError:
			error = True
		else:
			error = False

		assert error

		callback = Mock()
		handle   = resource.subscribe(callback)

		resource.update()
		callback.assert_called_once_with(None)
		resource.unsubscribe(handle)

		resource.update()
		callback.assert_called_once_with(None)

	# Cancellation inside dispatch suppresses a listener that has not run yet.
	# ----------------------------------------------------------------------
	@classmethod
	def test_cancel_during_dispatch(cls):
		resource = a.Resource()
		callback = Mock()

		cancel_second = Mock()
		first         = resource.subscribe(cancel_second)
		second        = resource.subscribe(callback)
		cancel_second.side_effect = lambda changed: resource.unsubscribe(second)

		resource.update()
		resource.update()

		assert callback.call_count == 0
		resource.unsubscribe(first)
		assert not resource.is_subscribed()

	# A failing externally observed listener must not suppress its neighbors.
	# ----------------------------------------------------------------------
	@classmethod
	def test_callback_failure_isolation(cls):
		with tempfile.TemporaryDirectory() as root:
			file     = a.File(a, os.path.join(root, 'failure.txt'), 'almasi.failure')
			service  = a.services.Filesystem
			callback = Mock()

			with patch.object(type(service), '_watch', return_value=None):
				first  = file.subscribe(Mock(side_effect=ValueError('intentional')))
				second = file.subscribe(callback)

				try:
					with patch('almasi.a.lib.resource.logging.exception') as report:
						file.update({'failure.txt': 'modified'})

					callback.assert_called_once_with({'failure.txt': 'modified'})
					report.assert_called_once_with('Subscription callback failed')
				finally:
					file.unsubscribe(first)
					file.unsubscribe(second)

	# An already running callback does not prevent cancellation.
	# ----------------------------------------------------------------------
	@classmethod
	def test_nonblocking_cancel(cls):
		resource = a.Resource()
		started  = threading.Event()
		release  = threading.Event()
		callback = Mock(side_effect=lambda changed: (started.set(), release.wait(2)))
		handle   = resource.subscribe(callback)
		worker   = threading.Thread(target=resource.update)
		worker.start()

		try:
			assert started.wait(2)
			resource.unsubscribe(handle)
			resource.update()
		finally:
			release.set()
			worker.join(2)

		assert not worker.is_alive()
		callback.assert_called_once_with(None)

	# Keep the generic read route compatible with file and directory APIs.
	# --------------------------------------------------------------------------
	@classmethod
	def test_resource_read(cls):
		with tempfile.TemporaryDirectory() as root:
			directory = a.Directory(a, root, 'almasi.assets')
			directory.write('notes.txt', 'text')
			file = next(item for item in directory if item.get_name() == 'notes.txt')

			assert isinstance(file, a.Resource)
			assert file.read() == 'text'
			assert directory.read() is directory
			assert directory.read('notes.txt') == 'text'

	# Reject computed or unrelated resources at the filesystem boundary.
	# --------------------------------------------------------------------------
	@classmethod
	def test_filesystem_only_observation(cls):
		service = a.services.Filesystem

		try:
			service.observe(a.Resource())
		except TypeError:
			error = True
		else:
			error = False

		assert error

	# Invalidate external namespace caches before sending the change hint.
	# --------------------------------------------------------------------------
	@classmethod
	def test_file_and_directory_notifications(cls):
		with tempfile.TemporaryDirectory() as root:
			directory = a.Directory(a, root, 'almasi.assets')
			directory.write('notes.txt', 'before')
			file      = next(item for item in directory if item.get_name() == 'notes.txt')
			service   = a.services.Filesystem
			got_file  = []
			got_dir   = []
			path      = directory.join('notes.txt')

			assert directory.notes == 'before'
			assert file.load() == 'before'

			with patch.object(type(service), '_watch', return_value=None):
				file_handle = file.subscribe(got_file.append)
				dir_handle  = directory.subscribe(got_dir.append)

				with open(path, 'w', encoding='utf-8') as stream:
					stream.write('after')

				service._changed_paths(root, {path: 'modified'})
				assert len(got_file) == 1
				assert next(iter(got_file[0].values())) == 'modified'
				assert file.load() == 'after'

				service._changed_paths(os.path.dirname(root), {path: 'modified'})
				assert len(got_dir) == 1
				assert directory.notes == 'after'

				file.unsubscribe(file_handle)
				directory.unsubscribe(dir_handle)

	# Resolve symlinked event roots to the same identity as watched roots.
	# --------------------------------------------------------------------------
	@classmethod
	def test_symlinked_root_notifications(cls):
		with tempfile.TemporaryDirectory() as parent:
			root  = os.path.realpath(os.path.join(parent, 'actual'))
			alias = os.path.join(parent, 'alias')
			os.mkdir(root)
			os.symlink(root, alias)

			path = os.path.join(root, 'notes.txt')

			with open(path, 'w', encoding='utf-8') as stream:
				stream.write('before')

			file    = a.File(a, path, 'almasi.symlinked')
			service = a.services.Filesystem
			events  = []

			with patch.object(type(service), '_watch', return_value=None):
				handle = file.subscribe(events.append)
				service._changed_paths(alias, {os.path.join(alias, 'notes.txt'): 'modified'})
				assert events == [{'notes.txt': 'modified'}]
				file.unsubscribe(handle)

	# Keep a directory subscribed across removal and subsequent recreation.
	# --------------------------------------------------------------------------
	@classmethod
	def test_directory_removal_and_recreation(cls):
		with tempfile.TemporaryDirectory() as parent:
			root      = os.path.join(parent, 'foo')
			directory = a.Directory(a, root, 'almasi.foo')
			service   = a.services.Filesystem
			events    = []
			os.mkdir(root)

			with patch.object(type(service), '_watch', return_value=None):
				handle = directory.subscribe(events.append)

				shutil.rmtree(root)
				service._changed_paths(parent, {root: 'deleted'})
				assert events[-1] == {'foo': 'deleted'}
				assert directory.is_subscribed()

				os.mkdir(root)
				service._changed_paths(parent, {root: 'created'})
				assert events[-1] == {'foo': 'created'}

				directory.unsubscribe(handle)
				assert not directory.is_subscribed()

	# Match recursive changes and preserve more than one thousand paths.
	# --------------------------------------------------------------------------
	@classmethod
	def test_recursive_directory_changes_without_limit(cls):
		with tempfile.TemporaryDirectory() as parent:
			root      = os.path.join(parent, 'foo')
			directory = a.Directory(a, root, 'almasi.foo')
			service   = a.services.Filesystem
			events    = []
			os.mkdir(root)

			with patch.object(type(service), '_watch', return_value=None):
				handle = directory.subscribe(events.append)

				changes = {
					os.path.join(root, 'nested', f'item_{index}.js'): 'modified'
					for index in range(1001)
				}
				service._changed_paths(parent, changes)
				assert len(events) == 1
				assert len(events[0]) == 1001
				assert events[0]['foo/nested/item_500.js'] == 'modified'

				directory.unsubscribe(handle)

	# Moving interest between resources releases the previous OS observation.
	# --------------------------------------------------------------------------
	@classmethod
	def test_move_and_cancel_subscription(cls):
		with tempfile.TemporaryDirectory() as root:
			one_path = os.path.join(root, 'one.txt')
			two_path = os.path.join(root, 'two.txt')

			for path in (one_path, two_path):
				with open(path, 'w', encoding='utf-8') as stream:
					stream.write('before')

			one     = a.File(a, one_path, 'almasi.one')
			two     = a.File(a, two_path, 'almasi.two')
			service = a.services.Filesystem
			events  = []

			with patch.object(type(service), '_watch', return_value=None):
				handle = one.subscribe(events.append)
				one.unsubscribe(handle)
				handle = two.subscribe(events.append)
				assert one not in service._resources
				assert two in service._resources

				service._changed_paths(root, {one_path: 'modified'})
				assert not events
				service._changed_paths(root, {two_path: 'modified'})
				assert len(events) == 1

				two.unsubscribe(handle)
				two.unsubscribe(handle)
				assert os.path.realpath(root) not in service._watchers
				assert one not in service._resources
				assert two not in service._resources

	# Share one OS watcher across subscriptions and release it with the last.
	# --------------------------------------------------------------------------
	@classmethod
	def test_shared_watcher_lifetime(cls):
		with tempfile.TemporaryDirectory() as root:
			path = os.path.join(root, 'shared.txt')

			with open(path, 'w', encoding='utf-8') as stream:
				stream.write('initial')

			file     = a.File(a, path, 'almasi.shared')
			service  = a.services.Filesystem
			first    = []
			second   = []

			with patch.object(type(service), '_watch', return_value=None):
				left  = file.subscribe(first.append)
				right = file.subscribe(second.append)

				assert os.path.realpath(root) in service._watchers
				service._changed_paths(root, {path: 'modified'})
				assert first == [{'shared.txt': 'modified'}]
				assert second == [{'shared.txt': 'modified'}]

				file.unsubscribe(left)
				assert os.path.realpath(root) in service._watchers

				service._changed_paths(root, {path: 'modified'})
				assert len(first) == 1
				assert len(second) == 2

				file.unsubscribe(right)
				assert os.path.realpath(root) not in service._watchers
				assert file not in service._resources

	# Preserve one change per path in an unordered OS event batch.
	# --------------------------------------------------------------------------
	@classmethod
	def test_event_coalescing(cls):
		with tempfile.TemporaryDirectory() as root:
			service = a.services.Filesystem
			path    = os.path.join(root, 'created.js')
			hidden  = os.path.join(root, '.almasi-temp.js')

			with open(path, 'w', encoding='utf-8') as stream:
				stream.write('ok')

			changes = service._changes({
				(Change.added, path),
				(Change.modified, path),
				(Change.deleted, hidden)
			})
			assert changes == {path: 'created'}

	# An overridden inherited file must not notify for hidden parent edits.
	# --------------------------------------------------------------------------
	@classmethod
	def test_inherited_override_switch(cls):
		tests = a.tests

		with tempfile.TemporaryDirectory() as parent_root, tempfile.TemporaryDirectory() as child_root:
			parent = tests.TestFilesystem._library('resource_parent_subscribe', parent_root, a.A)
			child  = tests.TestFilesystem._library('resource_child_subscribe', child_root, type(parent))
			parent.mkdir('shared').write('note.md', 'inherited')
			face   = child.mkdir('shared')
			file   = face.__resolve__('note.md')
			events = []
			source = a.services.Filesystem
			p_path = parent.shared.join('note.md')
			c_path = face.join('note.md')

			assert file.get_lib() is parent
			assert file._namespace_lib is child

			with patch.object(type(source), '_watch', return_value=None):
				handle = file.subscribe(events.append)

				parent.shared.write('note.md', 'changed')
				source._changed_paths(parent.__path__, {p_path: 'modified'})
				assert len(events) == 1

				face.write('note.md', 'local')
				source._changed_paths(child.__path__, {c_path: 'created'})
				assert len(events) == 2

				parent.shared.write('note.md', 'hidden')
				source._changed_paths(parent.__path__, {p_path: 'modified'})
				assert len(events) == 2

				os.remove(c_path)
				source._changed_paths(child.__path__, {c_path: 'deleted'})
				assert len(events) == 3

				file.unsubscribe(handle)

	# Resolve inherited unregistered file extensions without plugin filtering.
	# --------------------------------------------------------------------------
	@classmethod
	def test_unknown_extension_override_visibility(cls):
		tests = a.tests

		with tempfile.TemporaryDirectory() as parent_root, tempfile.TemporaryDirectory() as child_root:
			parent = tests.TestFilesystem._library('binary_parent_subscribe', parent_root, a.A)
			child  = tests.TestFilesystem._library('binary_child_subscribe', child_root, type(parent))
			parent.mkdir('static')
			child.mkdir('static')

			parent_path = parent.static.join('logo.opaque')
			child_path  = child.static.join('logo.opaque')

			with open(parent_path, 'wb') as stream:
				stream.write(b'inherited')

			file = a.File(parent, parent_path, 'binary_child_subscribe.static.logo')
			file._namespace_lib = child
			events = []
			source = a.services.Filesystem

			with patch.object(type(source), '_watch', return_value=None):
				handle = file.subscribe(events.append)
				assert source._effective(file) == parent_path

				with open(child_path, 'wb') as stream:
					stream.write(b'local')

				source._changed_paths(child.__path__, {child_path: 'created'})
				assert source._effective(file) == child_path
				assert len(events) == 1

				with open(parent_path, 'wb') as stream:
					stream.write(b'hidden')

				source._changed_paths(parent.__path__, {parent_path: 'modified'})
				assert len(events) == 1

				os.unlink(child_path)
				source._changed_paths(child.__path__, {child_path: 'deleted'})
				assert source._effective(file) == parent_path
				assert len(events) == 2
				file.unsubscribe(handle)

	# Forks keep separate resource identities under one physical observer.
	# ----------------------------------------------------------------------
	@classmethod
	def test_fork_resource_isolation(cls):
		with tempfile.TemporaryDirectory() as root:
			first   = a.fork('filesystem_first_' + uuid.uuid4().hex)
			second  = a.fork('filesystem_second_' + uuid.uuid4().hex)
			service = a.services.Filesystem
			path    = os.path.join(root, 'item.txt')
			one     = a.File(first, path, 'almasi.item')
			two     = a.File(second, path, 'almasi.item')
			events  = []

			with patch.object(type(service), '_watch', return_value=None):
				first_id  = one.subscribe(events.append)
				second_id = two.subscribe(events.append)

				try:
					assert one in service._resources
					assert two in service._resources
					assert one._namespace_lib is first
					assert two._namespace_lib is second
					assert os.path.realpath(root) in service._watchers

					one.unsubscribe(first_id)
					assert one not in service._resources
					assert two in service._resources
					assert os.path.realpath(root) in service._watchers

					two.update({'item.txt': 'modified'})
					assert events == [{'item.txt': 'modified'}]
				finally:
					one.unsubscribe(first_id)
					two.unsubscribe(second_id)

				assert os.path.realpath(root) not in service._watchers

	# Nested filesystem notifications keep each batch's own change details.
	# --------------------------------------------------------------------------
	@classmethod
	def test_reentrant_filesystem_payload(cls):
		with tempfile.TemporaryDirectory() as root:
			file    = a.File(a, os.path.join(root, 'nested.txt'), 'almasi.nested')
			service = a.services.Filesystem
			events  = []

			def callback(resources):
				events.append(resources)

				if resources['nested.txt'] == 'created':
					file.update({'nested.txt': 'deleted'})

			with patch.object(type(service), '_watch', return_value=None):
				handle = file.subscribe(callback)
				file.update({'nested.txt': 'created'})

				assert events == [
					{'nested.txt': 'created'},
					{'nested.txt': 'deleted'}
				]
				file.unsubscribe(handle)

	# Concurrent producers do not exchange or overwrite filesystem metadata.
	# --------------------------------------------------------------------------
	@classmethod
	def test_concurrent_filesystem_payload(cls):
		with tempfile.TemporaryDirectory() as root:
			file     = a.File(a, os.path.join(root, 'parallel.txt'), 'almasi.parallel')
			service  = a.services.Filesystem
			barrier  = threading.Barrier(2)
			received = []

			def callback(resources):
				barrier.wait(timeout=2)
				received.append(resources)

			with patch.object(type(service), '_watch', return_value=None):
				handle  = file.subscribe(callback)
				threads = [
					threading.Thread(
						target = file.update,
						args   = ({'parallel.txt': change},)
					)
					for change in ('modified', 'deleted')
				]

				for thread in threads:
					thread.start()

				for thread in threads:
					thread.join(timeout=3)

				assert all(not thread.is_alive() for thread in threads)
				assert {entry['parallel.txt'] for entry in received} == {'modified', 'deleted'}
				file.unsubscribe(handle)

	# The real watchfiles producer observes an external file modification.
	# --------------------------------------------------------------------------
	@classmethod
	def test_real_watchfiles_delivery(cls):
		with tempfile.TemporaryDirectory() as root:
			path = os.path.join(root, 'observed.txt')
			with open(path, 'w', encoding='utf-8') as stream:
				stream.write('before')

			file     = a.File(a, path, 'almasi.observed')
			received = threading.Event()
			events   = []

			handle = file.subscribe(lambda changed: (events.append(changed), received.set()))

			try:
				time.sleep(0.3)
				for index in range(6):
					if not received.is_set():
						with open(path, 'w', encoding='utf-8') as stream:
							stream.write(str(index))
						received.wait(timeout=0.6)

				assert received.is_set()
				assert any('observed.txt' in key for event in events for key in event)
			finally:
				file.unsubscribe(handle)


if __name__ == '__main__':
	TestResourceSubscriptions.run()

	# Verify failed deployment holds events and successful retry publishes them.
	# ----------------------------------------------------------------------
	@classmethod
	def test_deferred_changes(cls):
		asyncio.run(cls._exercise_deferred_changes())

	# Exercise the observer boundary without a timing-dependent OS watcher.
	# ----------------------------------------------------------------------
	@classmethod
	async def _exercise_deferred_changes(cls):
		service = a.services.Filesystem

		with tempfile.TemporaryDirectory() as directory:
			root  = os.path.realpath(directory)
			path  = os.path.join(root, 'component.py')
			other = os.path.dirname(root)

			with patch.object(service, '_deliver_changes') as deliver:
				try:
					async with service.defer_changes(root):
						service._changed_paths(root, {path: 'created'})
						service._changed_paths(other, {other: 'modified'})
						deliver.assert_called_once_with(other, {other: 'modified'})
						raise RuntimeError('Dependency installation failed')
				except RuntimeError as error:
					assert str(error) == 'Dependency installation failed'

				service._changed_paths(root, {path: 'modified'})
				deliver.assert_called_once_with(other, {other: 'modified'})

				async with service.defer_changes(root):
					assert deliver.call_count == 1

				assert deliver.call_count == 2
				deliver.assert_called_with(root, {path: 'modified'})

				service._changed_paths(root, {path: 'deleted'})
				deliver.assert_called_with(root, {path: 'deleted'})
