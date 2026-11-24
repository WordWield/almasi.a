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

import os
import shutil
import tempfile
import threading
import time
import uuid

from unittest.mock import Mock, patch

from watchfiles import Change

import almasi


class TestResourceSubscriptions(almasi.Tester):

	# ==========================================================================
	# PUBLIC METHODS
	# ==========================================================================

	# Split common resource identity without losing the established file API.
	# --------------------------------------------------------------------------
	@classmethod
	def test_resource_hierarchy(cls):
		assert issubclass(almasi.File, almasi.FilesystemResource)
		assert issubclass(almasi.Directory, almasi.FilesystemResource)
		assert issubclass(almasi.FilesystemResource, almasi.Resource)
		assert issubclass(almasi.Resource, almasi.Module)
		assert issubclass(almasi.File, almasi.Module)
		assert issubclass(almasi.Directory, almasi.Module)
		assert almasi.Resource.__bases__ == (almasi.Module,)
		assert not issubclass(almasi.Directory, almasi.File)
		assert almasi.File.is_directory(almasi.File(almasi, __file__, 'almasi.file')) is False
		assert almasi.Directory(almasi, os.path.dirname(__file__), 'almasi.tests').is_directory() is True
		assert almasi.File.subscribe is almasi.Resource.subscribe
		assert almasi.Directory.subscribe is almasi.Resource.subscribe
		assert almasi.File.read is almasi.FilesystemResource.read
		assert almasi.Directory.read is almasi.FilesystemResource.read

	# Base resources have no dependency on filesystem APIs or runtime services.
	# --------------------------------------------------------------------------
	@classmethod
	def test_generic_resource_contract(cls):
		resource = almasi.Resource()

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
		handle.cancel()

		resource.update()
		callback.assert_called_once_with(None)

	# Cancellation inside dispatch suppresses a listener that has not run yet.
	# ----------------------------------------------------------------------
	@classmethod
	def test_cancel_during_dispatch(cls):
		resource = almasi.Resource()
		callback = Mock()

		first  = resource.subscribe(Mock())
		second = resource.subscribe(callback)
		first.callback.side_effect = lambda changed: second.cancel()

		resource.update()
		resource.update()

		assert callback.call_count == 0
		first.cancel()
		assert not resource.is_subscribed()

	# A failing externally observed listener must not suppress its neighbors.
	# ----------------------------------------------------------------------
	@classmethod
	def test_callback_failure_isolation(cls):
		with tempfile.TemporaryDirectory() as root:
			file     = almasi.File(almasi, os.path.join(root, 'failure.txt'), 'almasi.failure')
			service  = almasi.services.Filesystem
			callback = Mock()

			with patch.object(type(service), '_watch', return_value=None):
				first  = file.subscribe(Mock(side_effect=ValueError('intentional')))
				second = file.subscribe(callback)

				try:
					with patch('lib.resource.logging.exception') as report:
						file.update({'failure.txt': 'modified'})

					callback.assert_called_once_with({'failure.txt': 'modified'})
					report.assert_called_once_with('Subscription callback failed')
				finally:
					first.cancel()
					second.cancel()

	# An already running callback does not prevent cancellation.
	# ----------------------------------------------------------------------
	@classmethod
	def test_nonblocking_cancel(cls):
		resource = almasi.Resource()
		started  = threading.Event()
		release  = threading.Event()
		callback = Mock(side_effect=lambda changed: (started.set(), release.wait(2)))
		handle   = resource.subscribe(callback)
		worker   = threading.Thread(target=resource.update)
		worker.start()

		try:
			assert started.wait(2)
			handle.cancel()
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
			directory = almasi.Directory(almasi, root, 'almasi.assets')
			directory.write('notes.txt', 'text')
			file = next(item for item in directory if item.get_name() == 'notes.txt')

			assert isinstance(file, almasi.Resource)
			assert file.read() == 'text'
			assert directory.read() is directory
			assert directory.read('notes.txt') == 'text'

	# Reject computed or unrelated resources at the filesystem boundary.
	# --------------------------------------------------------------------------
	@classmethod
	def test_filesystem_only_observation(cls):
		service = almasi.services.Filesystem

		try:
			service.observe(almasi.Resource())
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
			directory = almasi.Directory(almasi, root, 'almasi.assets')
			directory.write('notes.txt', 'before')
			file      = next(item for item in directory if item.get_name() == 'notes.txt')
			service   = almasi.services.Filesystem
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

				file_handle.cancel()
				dir_handle.cancel()

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

			file    = almasi.File(almasi, path, 'almasi.symlinked')
			service = almasi.services.Filesystem
			events  = []

			with patch.object(type(service), '_watch', return_value=None):
				handle = file.subscribe(events.append)
				service._changed_paths(alias, {os.path.join(alias, 'notes.txt'): 'modified'})
				assert events == [{'notes.txt': 'modified'}]
				handle.cancel()

	# Keep a directory subscribed across removal and subsequent recreation.
	# --------------------------------------------------------------------------
	@classmethod
	def test_directory_removal_and_recreation(cls):
		with tempfile.TemporaryDirectory() as parent:
			root      = os.path.join(parent, 'foo')
			directory = almasi.Directory(almasi, root, 'almasi.foo')
			service   = almasi.services.Filesystem
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

				handle.cancel()
				assert not directory.is_subscribed()

	# Match recursive changes and preserve more than one thousand paths.
	# --------------------------------------------------------------------------
	@classmethod
	def test_recursive_directory_changes_without_limit(cls):
		with tempfile.TemporaryDirectory() as parent:
			root      = os.path.join(parent, 'foo')
			directory = almasi.Directory(almasi, root, 'almasi.foo')
			service   = almasi.services.Filesystem
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

				handle.cancel()

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

			one     = almasi.File(almasi, one_path, 'almasi.one')
			two     = almasi.File(almasi, two_path, 'almasi.two')
			service = almasi.services.Filesystem
			events  = []

			with patch.object(type(service), '_watch', return_value=None):
				handle = one.subscribe(events.append)
				handle.cancel()
				handle = two.subscribe(events.append)
				assert one not in service._resources
				assert two in service._resources

				service._changed_paths(root, {one_path: 'modified'})
				assert not events
				service._changed_paths(root, {two_path: 'modified'})
				assert len(events) == 1

				handle.cancel()
				handle.cancel()
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

			file     = almasi.File(almasi, path, 'almasi.shared')
			service  = almasi.services.Filesystem
			first    = []
			second   = []

			with patch.object(type(service), '_watch', return_value=None):
				left  = file.subscribe(first.append)
				right = file.subscribe(second.append)

				assert os.path.realpath(root) in service._watchers
				service._changed_paths(root, {path: 'modified'})
				assert first == [{'shared.txt': 'modified'}]
				assert second == [{'shared.txt': 'modified'}]

				left.cancel()
				assert os.path.realpath(root) in service._watchers

				service._changed_paths(root, {path: 'modified'})
				assert len(first) == 1
				assert len(second) == 2

				right.cancel()
				assert os.path.realpath(root) not in service._watchers
				assert file not in service._resources

	# Preserve one change per path in an unordered OS event batch.
	# --------------------------------------------------------------------------
	@classmethod
	def test_event_coalescing(cls):
		with tempfile.TemporaryDirectory() as root:
			service = almasi.services.Filesystem
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
		from almasi import tests

		with tempfile.TemporaryDirectory() as parent_root, tempfile.TemporaryDirectory() as child_root:
			parent = tests.TestFilesystem._library('resource_parent_subscribe', parent_root, almasi.A)
			child  = tests.TestFilesystem._library('resource_child_subscribe', child_root, type(parent))
			parent.mkdir('shared').write('note.md', 'inherited')
			face   = child.mkdir('shared')
			file   = face.__resolve__('note.md')
			events = []
			source = child.services.Filesystem
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

				handle.cancel()

	# Resolve inherited unregistered file extensions without plugin filtering.
	# --------------------------------------------------------------------------
	@classmethod
	def test_unknown_extension_override_visibility(cls):
		from almasi import tests

		with tempfile.TemporaryDirectory() as parent_root, tempfile.TemporaryDirectory() as child_root:
			parent = tests.TestFilesystem._library('binary_parent_subscribe', parent_root, almasi.A)
			child  = tests.TestFilesystem._library('binary_child_subscribe', child_root, type(parent))
			parent.mkdir('static')
			child.mkdir('static')

			parent_path = parent.static.join('logo.opaque')
			child_path  = child.static.join('logo.opaque')

			with open(parent_path, 'wb') as stream:
				stream.write(b'inherited')

			file = almasi.File(parent, parent_path, 'binary_child_subscribe.static.logo')
			file._namespace_lib = child
			events = []
			source = child.services.Filesystem

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
				handle.cancel()

	# A fork resolves its own concrete Filesystem singleton and registrations.
	# --------------------------------------------------------------------------
	@classmethod
	def test_fork_service_isolation(cls):
		with tempfile.TemporaryDirectory() as root:
			first  = almasi.fork('filesystem_first_' + uuid.uuid4().hex)
			second = almasi.fork('filesystem_second_' + uuid.uuid4().hex)
			one    = first.services.Filesystem
			two    = second.services.Filesystem

			assert one is not two
			assert type(one) is not type(two)

			with patch.object(type(one), '_watch', return_value=None):
				file   = almasi.File(first, os.path.join(root, 'item.txt'), 'almasi.item')
				handle = file.subscribe(lambda changed: None)
				assert file in one._resources
				assert not two._resources
				handle.cancel()
				assert not one._watchers

	# Nested filesystem notifications keep each batch's own change details.
	# --------------------------------------------------------------------------
	@classmethod
	def test_reentrant_filesystem_payload(cls):
		with tempfile.TemporaryDirectory() as root:
			file    = almasi.File(almasi, os.path.join(root, 'nested.txt'), 'almasi.nested')
			service = almasi.services.Filesystem
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
				handle.cancel()

	# Concurrent producers do not exchange or overwrite filesystem metadata.
	# --------------------------------------------------------------------------
	@classmethod
	def test_concurrent_filesystem_payload(cls):
		with tempfile.TemporaryDirectory() as root:
			file     = almasi.File(almasi, os.path.join(root, 'parallel.txt'), 'almasi.parallel')
			service  = almasi.services.Filesystem
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
				handle.cancel()

	# The real watchfiles producer observes an external file modification.
	# --------------------------------------------------------------------------
	@classmethod
	def test_real_watchfiles_delivery(cls):
		with tempfile.TemporaryDirectory() as root:
			path = os.path.join(root, 'observed.txt')
			with open(path, 'w', encoding='utf-8') as stream:
				stream.write('before')

			file     = almasi.File(almasi, path, 'almasi.observed')
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
				handle.cancel()


if __name__ == '__main__':
	TestResourceSubscriptions.run()
