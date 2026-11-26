# ==============================================================================
# FILESYSTEM SERVICE
# ==============================================================================
# PURPOSE:
# Observe effective sets of files and deliver their changes.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Observation, effective file membership and the observation context.
# Delegates: Registration and delivery to Resource, OS events to watchfiles,
# and invalidation to the affected carriers.
# ==============================================================================

import asyncio
import logging
import os
import threading

from concurrent.futures import Future
from contextlib         import asynccontextmanager

from watchfiles import awatch

from almasi import a


class Filesystem(a.Singleton):

	# ======================================================================
	# FRAMEWORK METHODS
	# ======================================================================

	# Run subscriptions, OS changes and deployment publication in one context.
	# ----------------------------------------------------------------------
	def __new__(cls):
		instance = super().__new__(cls)

		if '_loop' not in instance.__dict__:
			logging.getLogger('watchfiles.main').setLevel(logging.WARNING)

			instance._resources  = {}
			instance._watchers   = {}
			instance._deferred   = {}
			instance._defer_lock = asyncio.Lock()
			instance._loop       = asyncio.new_event_loop()

			threading.Thread(target=instance._loop.run_forever, daemon=True).start()

		return instance

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Identify the owning execution context, not the initiating caller.
	# ----------------------------------------------------------------------
	def _is_observation_context(self):
		try:
			result = asyncio.get_running_loop() is self._loop
		except RuntimeError:
			result = False

		return result

	# Express physical locations in local-first effective namespace order.
	# ----------------------------------------------------------------------
	def _get_locations(self, resource):
		path      = resource.get_path()
		namespace = resource.get_namespace()
		layers    = tuple(namespace.__instances__())
		relative  = None

		for layer in layers:
			root = os.path.realpath(layer.__path__)

			if os.path.commonpath((root, path)) == root:
				relative = os.path.relpath(path, root)
				break

		if relative is None:
			locations = {os.path.dirname(path): (resource.get_lib(), path)}
		else:
			locations = {}

			for layer in layers:
				root = os.path.realpath(layer.__path__)
				locations.setdefault(root, (layer, os.path.join(root, relative)))

		return {root: (layer, os.path.normpath(base)) for root, (layer, base) in locations.items() if os.path.isdir(root)}

	# Discover files only at subscription or in an affected new subtree.
	# ----------------------------------------------------------------------
	def _get_initial_files(self, base, path):
		files = {}

		if os.path.isfile(path):
			files[os.path.relpath(path, base).replace(os.sep, '/')] = path
		elif os.path.isdir(path):
			for directory, _, names in os.walk(path):
				for name in names:
					file = os.path.join(directory, name)
					files[os.path.relpath(file, base).replace(os.sep, '/')] = file

		return files

	# Select the first existing source of each logical file.
	# ----------------------------------------------------------------------
	def _get_effective_files(self, resource, locations):
		files = {}

		for _, base in locations.values():
			if resource.is_directory():
				found = self._get_initial_files(base, base)
			else:
				found = {'.': base} if os.path.isfile(base) else {}

			for name, path in found.items():
				files.setdefault(name, path)

		return files

	# Resolve one logical filename without walking unrelated directories.
	# ----------------------------------------------------------------------
	def _resolve(self, name, locations):
		result = None

		for _, base in locations.values():
			path = os.path.normpath(os.path.join(base, name))

			if os.path.isfile(path):
				result = path
				break

		return result

	# Keep one native watcher per physical root, regardless of subscribers.
	# ----------------------------------------------------------------------
	async def _watch(self, root):
		try:
			async for changes in awatch(root, debounce=100, step=50, rust_timeout=500):
				self._process_changed_paths(root, {os.path.realpath(path) for _, path in changes})
		except Exception:
			logging.exception('Filesystem observer failed: %s', root)

	# Match native observation lifetime to effective resource locations.
	# ----------------------------------------------------------------------
	def _reconcile(self):
		roots = {root for locations, _ in self._resources.values() for root in locations}

		for root in roots - self._watchers.keys():
			self._watchers[root] = self._loop.create_task(self._watch(root))

		for root in self._watchers.keys() - roots:
			self._watchers.pop(root).cancel()

	# Find logical files affected by one physical event, including subtrees.
	# ----------------------------------------------------------------------
	def _get_affected_names(self, resource, base, path, files):
		names = set()

		if resource.is_directory():
			if path == base or base.startswith(path + os.sep):
				names.update(files)
				names.update(self._get_initial_files(base, base))
			elif path.startswith(base + os.sep):
				name = os.path.relpath(path, base).replace(os.sep, '/')
				if name in files and os.path.isfile(path):
					names.add(name)
				else:
					names.update(key for key in files if key == name or key.startswith(name + '/'))
					names.update(self._get_initial_files(base, path))
		elif path == base or base.startswith(path + os.sep):
			names.add('.')

		return names

	# Invalidate physical source caches before publishing effective changes.
	# ----------------------------------------------------------------------
	def _deliver_changes(self, root, paths):
		observed = tuple(
			(resource, locations, files)
			for resource, (locations, files) in self._resources.items()
			if root in locations
		)

		layers = {locations[root][0] for _, locations, _ in observed}

		for layer in layers:
			for path in paths:
				a.Directory(layer, os.path.dirname(path), layer.__name__).invalidate(os.path.basename(path))

		for resource, locations, files in observed:
			if resource in self._resources:
				_, base = locations[root]
				names   = {name for path in paths for name in self._get_affected_names(resource, base, path, files)}
				changes = {}

				for name in names:
					old = files.get(name)
					new = self._resolve(name, locations)

					if new != old:
						if new is None:
							del files[name]
							changes[name] = 'deleted'
						else:
							files[name]  = new
							changes[name] = 'created' if old is None else 'modified'
					elif new in paths:
						changes[name] = 'modified'

				if changes:
					if isinstance(resource, a.File):
						resource.invalidate()

					resource.update(changes)

	# Buffer physical changes only while their deployment is being prepared.
	# ----------------------------------------------------------------------
	def _process_changed_paths(self, root, paths):
		root  = os.path.realpath(root)
		paths = {os.path.realpath(path) for path in paths}

		if root in self._deferred:
			self._deferred[root].update(paths)
		else:
			self._deliver_changes(root, paths)

	# Publish existing files to the new registration.
	# ----------------------------------------------------------------------
	def _subscribe(self, future, resource, callback):
		try:
			subscription_id = a.Resource.subscribe(resource, callback)
			_, files       = self._resources[resource]
			changes        = {name: 'created' for name in files}
		except Exception as error:
			future.set_exception(error)
		else:
			future.set_result(subscription_id)
			resource.notify_subscription(subscription_id, changes)

	# Hold or release notifications in the same context as OS events.
	# ----------------------------------------------------------------------
	async def _defer(self, root, active):
		if active:
			self._deferred.setdefault(root, set())
		else:
			paths = self._deferred.pop(root)

			if paths:
				self._deliver_changes(root, paths)

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Register both file and directory listeners through the observation context.
	# ----------------------------------------------------------------------
	def subscribe(self, resource, callback):
		'''Return the Resource registration ID; deliver existing files as created
		and subsequent changes in the Filesystem observation context.'''
		future = Future()

		if self._is_observation_context():
			self._subscribe(future, resource, callback)
		else:
			self._loop.call_soon_threadsafe(self._subscribe, future, resource, callback)

		return future.result()

	# Reconcile observation when the Resource's registration state changes.
	# ----------------------------------------------------------------------
	def observe(self, resource):
		if isinstance(resource, a.FilesystemResource):
			if self._is_observation_context():
				if resource.is_subscribed():
					if resource not in self._resources:
						locations = self._get_locations(resource)
						self._resources[resource] = (locations, self._get_effective_files(resource, locations))
				else:
					self._resources.pop(resource, None)

				self._reconcile()
			else:
				self._loop.call_soon_threadsafe(self.observe, resource)
		else:
			raise TypeError('Filesystem observation requires a FilesystemResource')

	# Hold publication for a physical root until asynchronous preparation succeeds.
	# ----------------------------------------------------------------------
	@asynccontextmanager
	async def defer_changes(self, root):
		'''Retain notifications on failure and publish on a successful retry.
		Other roots continue to deliver normally.'''
		root = os.path.realpath(root)

		async with self._defer_lock:
			await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(self._defer(root, True), self._loop))
			yield
			await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(self._defer(root, False), self._loop))
