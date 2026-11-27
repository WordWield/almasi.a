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

from typing        import Generic, get_args, get_origin, get_type_hints
from unittest.mock import Mock, patch

from almasi import a


class TestResourceSubscriptions(a.Tester):

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Dispatch synthetic OS paths through the actual observation context.
	# ----------------------------------------------------------------------
	@classmethod
	async def _publish(
		cls,
		service,
		root  = None,
		paths = None
	):
		if root is not None:
			service._process_changed_paths(root, paths)

	# Wait for previously scheduled source operations before assertions.
	# ----------------------------------------------------------------------
	@classmethod
	def _sync(
		cls,
		service,
		root  = None,
		paths = None
	):
		asyncio.run_coroutine_threadsafe(cls._publish(service, root, paths), service._loop).result(timeout=5)

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
		assert a.Resource.__bases__ == (a.Module, Generic)
		assert not issubclass(a.Directory, a.File)
		assert a.File.is_directory(a.File(a, __file__, 'almasi.file')) is False
		assert a.Directory(a, os.path.dirname(__file__), 'almasi.tests').is_directory() is True
		assert a.File.subscribe is a.Directory.subscribe is a.FilesystemResource.subscribe
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

	# Type declarations describe reads without creating another resource class.
	# --------------------------------------------------------------------------
	@classmethod
	def test_resource_type_parameter(cls):
		declaration = a.Resource[int]
		assert get_origin(declaration) is a.Resource
		assert get_args(declaration) == (int,)
		assert get_type_hints(a.Resource.read)['return'] is a.Resource.__parameters__[0]

		resource = a.resources.Writable(42)
		assert isinstance(resource, a.Resource)
		assert resource.read() == 42

		events = []
		handle = resource.subscribe(events.append)

		resource.write(None)
		assert resource.read() is None
		assert events == [None]
		resource.unsubscribe(handle)

		resource.write('unchanged runtime contract')
		assert resource.read() == 'unchanged runtime contract'
		assert events == [None]

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
				cls._sync(service)
				callback.reset_mock()

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

				cls._sync(service, root, {path: 'modified'})
				assert got_file == [{'.': 'created'}, {'.': 'modified'}]
				assert file.load() == 'after'

				cls._sync(service, os.path.dirname(root), {path: 'modified'})
				assert got_dir == [{'notes.txt': 'created'}, {'notes.txt': 'modified'}]
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
				cls._sync(service, alias, {os.path.join(alias, 'notes.txt'): 'modified'})
				assert events == [{'.': 'created'}, {'.': 'modified'}]
				file.unsubscribe(handle)

	# Each new directory listener receives its own recursive initial batch.
	# ----------------------------------------------------------------------
	@classmethod
	def test_directory_initial_changes(cls):
		with tempfile.TemporaryDirectory() as root:
			directory = a.Directory(a, root, 'almasi.initial')
			service   = a.services.Filesystem
			first     = []
			second    = []
			os.mkdir(os.path.join(root, 'nested'))

			for name in ('one.py', 'nested/two.txt', '.almasi-temp'):
				with open(os.path.join(root, name), 'w', encoding='utf-8') as stream:
					stream.write('content')

			with patch.object(type(service), '_watch', return_value=None):
				left  = directory.subscribe(first.append)
				right = directory.subscribe(second.append)
				cls._sync(service)

				try:
					assert first == second == [{'one.py': 'created', 'nested/two.txt': 'created', '.almasi-temp': 'created'}]
					directory.update({'one.py': 'modified'})
					assert first == second == [
						{'one.py': 'created', 'nested/two.txt': 'created', '.almasi-temp': 'created'},
						{'one.py': 'modified'}
					]
				finally:
					directory.unsubscribe(left)
					directory.unsubscribe(right)

	# Initial and live failures follow the same Resource delivery contract.
	# ----------------------------------------------------------------------
	@classmethod
	def test_directory_callback_failure(cls):
		with tempfile.TemporaryDirectory() as root:
			directory = a.Directory(a, root, 'almasi.initial')
			service   = a.services.Filesystem
			callback  = Mock()
			failure   = Mock(side_effect=ValueError('intentional'))

			with patch.object(type(service), '_watch', return_value=None):
				with patch('almasi.a.lib.resource.logging.exception') as report:
					left  = directory.subscribe(callback)
					right = directory.subscribe(failure)

					try:
						cls._sync(service)
						path = directory.join('one.py')

						with open(path, 'w') as stream:
							stream.write('content')

						cls._sync(service, os.path.dirname(root), {path})
						assert callback.call_count == failure.call_count == report.call_count == 2
					finally:
						directory.unsubscribe(left)
						directory.unsubscribe(right)

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
			path = os.path.join(root, 'one.txt')

			with open(path, 'w') as stream:
				stream.write('before')

			with patch.object(type(service), '_watch', return_value=None):
				handle = directory.subscribe(events.append)
				cls._sync(service)

				shutil.rmtree(root)
				cls._sync(service, parent, {root: 'deleted'})
				assert events[-1] == {'one.txt': 'deleted'}
				assert directory.is_subscribed()

				os.mkdir(root)
				with open(path, 'w') as stream:
					stream.write('after')

				cls._sync(service, parent, {root})
				assert events[-1] == {'one.txt': 'created'}

				directory.unsubscribe(handle)
				assert not directory.is_subscribed()

	# Report changes to an observed file's ancestor in the same coordinates.
	# ----------------------------------------------------------------------
	@classmethod
	def test_file_ancestor_notification(cls):
		with tempfile.TemporaryDirectory() as root:
			parent = os.path.join(root, 'nested')
			path   = os.path.join(parent, 'note.txt')
			os.mkdir(parent)

			with open(path, 'w', encoding='utf-8') as stream:
				stream.write('before')

			file    = a.File(a, path, 'almasi.nested.note')
			service = a.services.Filesystem
			events  = []

			with patch.object(type(service), '_watch', return_value=None):
				handle = file.subscribe(events.append)

				try:
					shutil.rmtree(parent)
					cls._sync(service, parent, {parent: 'deleted'})
					assert events == [{'.': 'created'}, {'.': 'deleted'}]
				finally:
					file.unsubscribe(handle)

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

				os.mkdir(os.path.join(root, 'nested'))
				changes = {os.path.join(root, 'nested', f'item_{index}.js') for index in range(1001)}

				for path in changes:
					with open(path, 'w') as stream:
						stream.write('content')
				cls._sync(service, parent, changes)
				assert len(events) == 2
				assert events[0] == {}
				assert len(events[1]) == 1001
				assert events[1]['nested/item_500.js'] == 'created'

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
				cls._sync(service)
				events.clear()
				assert one not in service._resources
				assert two in service._resources

				cls._sync(service, root, {one_path: 'modified'})
				assert not events
				cls._sync(service, root, {two_path: 'modified'})
				assert len(events) == 1

				two.unsubscribe(handle)
				two.unsubscribe(handle)
				cls._sync(service)
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
				cls._sync(service, root, {path: 'modified'})
				assert first == [{'.': 'created'}, {'.': 'modified'}]
				assert second == first

				file.unsubscribe(left)
				assert os.path.realpath(root) in service._watchers

				cls._sync(service, root, {path: 'modified'})
				assert len(first) == 2
				assert len(second) == 3

				file.unsubscribe(right)
				cls._sync(service)
				assert os.path.realpath(root) not in service._watchers
				assert file not in service._resources

	# Existing and subsequent notifications share the same source context.
	# ----------------------------------------------------------------------
	@classmethod
	def test_same_observation_context(cls):
		with tempfile.TemporaryDirectory() as root:
			path = os.path.join(root, 'one.txt')

			with open(path, 'w') as stream:
				stream.write('before')

			file      = a.File(a, path, 'almasi.one')
			directory = a.Directory(a, root, 'almasi.files')
			service   = a.services.Filesystem
			file_log  = []
			dir_log   = []

			with patch.object(type(service), '_watch', return_value=None):
				left  = file.subscribe(lambda changes: file_log.append((threading.get_ident(), changes)))
				right = directory.subscribe(lambda changes: dir_log.append((threading.get_ident(), changes)))

				try:
					cls._sync(service)
					cls._sync(service, root, {path})
					cls._sync(service, os.path.dirname(root), {path})

					assert [changes for _, changes in file_log] == [{'.': 'created'}, {'.': 'modified'}]
					assert [changes for _, changes in dir_log] == [{'one.txt': 'created'}, {'one.txt': 'modified'}]
					assert len({identity for identity, _ in file_log + dir_log}) == 1
					assert file_log[0][0] != threading.get_ident()
				finally:
					file.unsubscribe(left)
					directory.unsubscribe(right)

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
			events     = []
			dir_events = []
			source     = a.services.Filesystem
			p_path     = parent.shared.join('note.md')
			c_path     = face.join('note.md')

			assert file.get_lib() is parent
			assert file._namespace_lib is child

			with patch.object(type(source), '_watch', return_value=None):
				handle     = file.subscribe(events.append)
				dir_handle = face.subscribe(dir_events.append)

				parent.shared.write('note.md', 'changed')
				cls._sync(source, parent.__path__, {p_path: 'modified'})
				assert events == [{'.': 'created'}, {'.': 'modified'}]
				assert dir_events == [{'note.md': 'created'}, {'note.md': 'modified'}]

				face.write('note.md', 'local')
				cls._sync(source, child.__path__, {c_path: 'created'})
				assert events[-1] == {'.': 'modified'}
				assert dir_events[-1] == {'note.md': 'modified'}
				assert len(events) == 3 and len(dir_events) == 3

				parent.shared.write('note.md', 'hidden')
				cls._sync(source, parent.__path__, {p_path: 'modified'})
				assert len(events) == 3 and len(dir_events) == 3

				os.remove(c_path)
				cls._sync(source, child.__path__, {c_path: 'deleted'})
				assert events[-1] == {'.': 'modified'}
				assert dir_events[-1] == {'note.md': 'modified'}
				assert len(events) == 4 and len(dir_events) == 4

				file.unsubscribe(handle)
				face.unsubscribe(dir_handle)

	# Invalidate a shared source once even when multiple namespaces observe it.
	# ----------------------------------------------------------------------
	@classmethod
	def test_shared_source_invalidation(cls):
		tests = a.tests

		with tempfile.TemporaryDirectory() as parent_root, tempfile.TemporaryDirectory() as child_root:
			parent = tests.TestFilesystem._library('shared_source_parent', parent_root, a.A)
			child  = tests.TestFilesystem._library('shared_source_child', child_root, type(parent))
			parent.mkdir('shared').write('notes.md', 'before')
			face    = child.mkdir('shared')
			path    = parent.shared.join('notes.md')
			service = a.services.Filesystem
			first   = []
			second  = []

			assert parent.shared.notes == face.notes == 'before'

			with patch.object(type(service), '_watch', return_value=None):
				parent_id = parent.shared.subscribe(first.append)
				child_id  = face.subscribe(second.append)

				try:
					with open(path, 'w', encoding='utf-8') as stream:
						stream.write('after')

					with patch.object(a.Directory, '_invalidate_children', autospec=True, side_effect=a.Directory._invalidate_children) as invalidate:
						cls._sync(service, parent.__path__, {path: 'modified'})
						assert invalidate.call_count == 1

					assert first == second == [{'notes.md': 'created'}, {'notes.md': 'modified'}]
					assert parent.shared.notes == face.notes == 'after'
				finally:
					parent.shared.unsubscribe(parent_id)
					face.unsubscribe(child_id)

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
				assert source._resources[file][1]['.'] == parent_path

				with open(child_path, 'wb') as stream:
					stream.write(b'local')

				cls._sync(source, child.__path__, {child_path: 'created'})
				assert source._resources[file][1]['.'] == child_path
				assert len(events) == 2

				with open(parent_path, 'wb') as stream:
					stream.write(b'hidden')

				cls._sync(source, parent.__path__, {parent_path: 'modified'})
				assert len(events) == 2

				os.unlink(child_path)
				cls._sync(source, child.__path__, {child_path: 'deleted'})
				assert source._resources[file][1]['.'] == parent_path
				assert len(events) == 3
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
				cls._sync(service)
				events.clear()

				try:
					assert one in service._resources
					assert two in service._resources
					assert one._namespace_lib is first
					assert two._namespace_lib is second
					assert os.path.realpath(root) in service._watchers

					one.unsubscribe(first_id)
					cls._sync(service)
					assert one not in service._resources
					assert two in service._resources
					assert os.path.realpath(root) in service._watchers

					two.update({'item.txt': 'modified'})
					assert events == [{'item.txt': 'modified'}]
				finally:
					one.unsubscribe(first_id)
					two.unsubscribe(second_id)
					cls._sync(service)

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

				if resources.get('nested.txt') == 'created':
					file.update({'nested.txt': 'deleted'})

			with patch.object(type(service), '_watch', return_value=None):
				handle = file.subscribe(callback)
				cls._sync(service)
				events.clear()
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
				if resources:
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
				assert received.wait(timeout=2)
				assert events == [{'.': 'created'}]
				received.clear()
				time.sleep(0.3)
				for index in range(6):
					if not received.is_set():
						with open(path, 'w', encoding='utf-8') as stream:
							stream.write(str(index))
						received.wait(timeout=0.6)

				assert received.is_set()
				assert any(event.get('.') == 'modified' for event in events)
			finally:
				file.unsubscribe(handle)


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
						cls._sync(service, root, {path: 'created'})
						cls._sync(service, other, {other: 'modified'})
						deliver.assert_called_once_with(other, {other})
						raise RuntimeError('Dependency installation failed')
				except RuntimeError as error:
					assert str(error) == 'Dependency installation failed'

				cls._sync(service, root, {path: 'modified'})
				deliver.assert_called_once_with(other, {other})

				async with service.defer_changes(root):
					assert deliver.call_count == 1

				assert deliver.call_count == 2
				deliver.assert_called_with(root, {path})

				cls._sync(service, root, {path: 'deleted'})
				deliver.assert_called_with(root, {path})


if __name__ == '__main__':
	TestResourceSubscriptions.run()
