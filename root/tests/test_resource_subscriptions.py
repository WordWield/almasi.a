# ==============================================================================
# TEST RESOURCE SUBSCRIPTIONS
# ==============================================================================
# Verify filesystem invalidations, resource scopes, inheritance and OS watching.
# ==============================================================================

import os
import shutil
import tempfile
import threading
import time
import uuid

from unittest.mock import patch

from watchfiles import Change

import a


class TestResourceSubscriptions(a.Tester):

	# ==========================================================================
	# PRIVATE METHODS
	# ==========================================================================

	# Quiesce actual OS watchers while testing deterministic source events.
	# --------------------------------------------------------------------------
	@classmethod
	def _threads(cls, service):
		for watcher in tuple(service._watchers.values()):
			watcher['thread'].join(timeout=2)

	# ==========================================================================
	# PUBLIC METHODS
	# ==========================================================================

	# Split common resource identity without losing the established file API.
	# --------------------------------------------------------------------------
	@classmethod
	def test_resource_hierarchy(cls):
		assert issubclass(a.File, a.Resource)
		assert issubclass(a.Directory, a.Resource)
		assert not issubclass(a.Directory, a.File)
		assert a.File.is_directory(a.File(a, __file__, 'a.file')) is False
		assert a.Directory(a, os.path.dirname(__file__), 'a.tests').is_directory() is True
		assert a.File.subscribe is a.Resource.subscribe
		assert a.Directory.subscribe is a.Resource.subscribe

	# Invalidate external namespace caches before sending the change hint.
	# --------------------------------------------------------------------------
	@classmethod
	def test_file_and_directory_notifications(cls):
		with tempfile.TemporaryDirectory() as root:
			directory = a.Directory(a, root, 'a.assets')
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
				cls._threads(service)

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

	# Keep a directory subscribed across removal and subsequent recreation.
	# --------------------------------------------------------------------------
	@classmethod
	def test_directory_removal_and_recreation(cls):
		with tempfile.TemporaryDirectory() as parent:
			root      = os.path.join(parent, 'foo')
			directory = a.Directory(a, root, 'a.foo')
			service   = a.services.Filesystem
			events    = []
			os.mkdir(root)

			with patch.object(type(service), '_watch', return_value=None):
				handle = directory.subscribe(events.append)
				cls._threads(service)

				shutil.rmtree(root)
				service._changed_paths(parent, {root: 'deleted'})
				assert events[-1] == {'foo': 'deleted'}
				assert handle._active

				os.mkdir(root)
				service._changed_paths(parent, {root: 'created'})
				assert events[-1] == {'foo': 'created'}

				handle.cancel()
				assert not handle._active

	# Match recursive changes and preserve more than one thousand paths.
	# --------------------------------------------------------------------------
	@classmethod
	def test_recursive_directory_changes_without_limit(cls):
		with tempfile.TemporaryDirectory() as parent:
			root      = os.path.join(parent, 'foo')
			directory = a.Directory(a, root, 'a.foo')
			service   = a.services.Filesystem
			events    = []
			os.mkdir(root)

			with patch.object(type(service), '_watch', return_value=None):
				handle = directory.subscribe(events.append)
				cls._threads(service)

				changes = {
					os.path.join(root, 'nested', f'item_{index}.js'): 'modified'
					for index in range(1001)
				}
				service._changed_paths(parent, changes)
				assert len(events) == 1
				assert len(events[0]) == 1001
				assert events[0]['foo/nested/item_500.js'] == 'modified'

				handle.cancel()

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
		from a import tests

		with tempfile.TemporaryDirectory() as parent_root, tempfile.TemporaryDirectory() as child_root:
			parent = tests.TestFilesystem._library('resource_parent_subscribe', parent_root, a.A)
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
				cls._threads(source)

				parent.shared.write('note.md', 'changed')
				source._changed_paths(parent_root, {p_path: 'modified'})
				assert len(events) == 1

				face.write('note.md', 'local')
				source._changed_paths(child_root, {c_path: 'created'})
				assert len(events) == 2

				parent.shared.write('note.md', 'hidden')
				source._changed_paths(parent_root, {p_path: 'modified'})
				assert len(events) == 2

				os.remove(c_path)
				source._changed_paths(child_root, {c_path: 'deleted'})
				assert len(events) == 3

				handle.cancel()

	# A fork resolves its own concrete Filesystem singleton and registrations.
	# --------------------------------------------------------------------------
	@classmethod
	def test_fork_service_isolation(cls):
		with tempfile.TemporaryDirectory() as root:
			first  = a.fork('filesystem_first_' + uuid.uuid4().hex)
			second = a.fork('filesystem_second_' + uuid.uuid4().hex)
			one    = first.services.Filesystem
			two    = second.services.Filesystem

			assert one is not two
			assert type(one) is not type(two)

			with patch.object(type(one), '_watch', return_value=None):
				file   = a.File(first, os.path.join(root, 'item.txt'), 'a.item')
				handle = file.subscribe(lambda changed: None)
				cls._threads(one)
				assert handle in one._subscriptions
				assert not two._subscriptions
				handle.cancel()
				assert not one._watchers

	# The real watchfiles producer observes an external file modification.
	# --------------------------------------------------------------------------
	@classmethod
	def test_real_watchfiles_delivery(cls):
		with tempfile.TemporaryDirectory() as root:
			path = os.path.join(root, 'observed.txt')
			with open(path, 'w', encoding='utf-8') as stream:
				stream.write('before')

			file     = a.File(a, path, 'a.observed')
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
