# ==============================================================================
# FILESYSTEM SERVICE
# ==============================================================================
# PURPOSE:
# Observe effective Almasi resources and invalidate cached namespace faces.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Filesystem watching, effective paths and cache invalidation.
# Delegates: Subscriber registrations and delivery to the observed resources.
# ==============================================================================

import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager

from watchfiles import Change, watch

from almasi import a


class Filesystem(a.Singleton):

	# ==========================================================================
	# FRAMEWORK METHODS
	# ==========================================================================

	# Share OS observers in the canonical service across resource namespaces.
	# --------------------------------------------------------------------------
	def __new__(cls):
		instance = super().__new__(cls)

		if '_resources' not in instance.__dict__:
			instance._observation_lock = threading.RLock()
			instance._resources        = {}
			instance._watchers         = {}
			instance._dispatch_lock    = threading.RLock()
			instance._defer_lock       = asyncio.Lock()
			instance._deferred_changes = {}

		return instance

	# ==========================================================================
	# PRIVATE METHODS
	# ==========================================================================

	# Find the physical source layer and its path relative to that layer.
	# --------------------------------------------------------------------------
	def _source(self, namespace, path):
		source = (None, namespace, None)

		for index, layer in enumerate(namespace.__instances__()):
			root = os.path.realpath(layer.__path__)

			if path == root or path.startswith(root + os.sep):
				source = (index, layer, os.path.relpath(path, root))
				break

		return source

	# Locate the effective source even when no format plugin handles the file.
	# Preserve Almasi's own resolver for known file and directory carriers.
	# --------------------------------------------------------------------------
	def _resolve(self, namespace, relative):
		parent = os.path.dirname(relative)
		route  = namespace.__name__ + ('.' + parent.replace(os.sep, '.') if parent else '')
		face   = a.Directory(namespace, os.path.join(namespace.__path__, parent), route)
		found  = face.__resolve__(os.path.basename(relative))
		result = found.get_path() if found is not None else None

		if result is None:
			for layer in namespace.__instances__():
				root      = os.path.realpath(layer.__path__)
				candidate = os.path.realpath(os.path.join(root, relative))

				if os.path.commonpath((root, candidate)) == root and os.path.isfile(candidate):
					result = candidate
					break

		return result

	# Keep the resolved source path to detect overridden files and removals.
	# --------------------------------------------------------------------------
	def _effective(self, namespace, path, relative):
		if relative is not None and relative != '.':
			path = self._resolve(namespace, relative)
		else:
			path = path if os.path.exists(path) else None

		return path

	# Observe all inherited roots or the parent of an external resource.
	# --------------------------------------------------------------------------
	def _roots_for(self, namespace, path, relative):
		if relative is not None:
			roots = {os.path.realpath(layer.__path__) for layer in namespace.__instances__()}
		else:
			roots = {os.path.dirname(path)}

		return {root for root in roots if os.path.isdir(root)}

	# Run one recursive watcher for each physical root needed by subscribers.
	# --------------------------------------------------------------------------
	def _watch(self, root, stop):
		try:
			for changes in watch(root, stop_event=stop, debounce=100, step=50, rust_timeout=500):
				paths = self._changes(changes)

				if paths and not stop.is_set():
					self._changed_paths(root, paths)
		except Exception:
			logging.exception('Filesystem observer failed: %s', root)

	# Collapse unordered OS events to one final observed status per path.
	# --------------------------------------------------------------------------
	def _changes(self, events):
		changes = {}

		for change, path in events:
			if not os.path.basename(path).startswith('.almasi-'):
				path   = os.path.abspath(path)
				status = 'created' if change == Change.added else 'deleted' if change == Change.deleted else 'modified'

				if path in changes:
					status = (
						'deleted' if not os.path.exists(path)
						else 'created' if 'created' in (status, changes[path])
						else 'modified'
					)

				changes[path] = status

		return changes

	# Reconcile OS watchers with the current set of observed resources.
	# ----------------------------------------------------------------------
	def _reconcile(self):
		roots = {root for entry in self._resources.values() for root in entry['roots']}

		for root in roots - self._watchers.keys():
			stop = threading.Event()
			threading.Thread(target=self._watch, args=(root, stop), daemon=True).start()
			self._watchers[root] = stop

		for root in self._watchers.keys() - roots:
			self._watchers.pop(root).set()

	# Ignore shadowed changes, while notifying when an override disappears.
	# --------------------------------------------------------------------------
	def _visible(self, namespace, path, index, relative):
		effective = self._resolve(namespace, relative)
		visible   = effective is None or effective == path

		if not visible:
			effective_index, _, _ = self._source(namespace, effective)
			visible = effective_index is not None and index < effective_index

		return visible

	# Hold notifications for a deployment root until its preparation succeeds.
	# --------------------------------------------------------------------------
	def _changed_paths(self, root, paths):
		root  = os.path.realpath(root)
		paths = {os.path.realpath(path): status for path, status in paths.items()}

		with self._dispatch_lock:
			if root in self._deferred_changes:
				self._deferred_changes[root].update(paths)
			else:
				self._deliver_changes(root, paths)

	# Map physical changes to subscribed resources and invalidate before dispatch.
	# --------------------------------------------------------------------------
	def _deliver_changes(self, root, paths):

		with self._observation_lock:
			observed = tuple(
				(resource, entry['path'])
				for resource, entry in self._resources.items()
				if root in entry['roots']
			)

		namespaces  = {resource._namespace_lib for resource, old in observed}
		sources     = {}
		visibility  = {}
		invalidated = set()

		for path in paths:
			for namespace in namespaces:
				index, layer, relative   = self._source(namespace, path)
				sources[namespace, path] = (index, relative)

				if (layer, path) not in invalidated:
					a.Directory(layer, os.path.dirname(path), layer.__name__)._invalidate_children(path)
					invalidated.add((layer, path))

		changed = {}

		for resource, old in observed:
			namespace      = resource._namespace_lib
			base           = resource.get_path()
			_, _, relative = self._source(namespace, base)
			is_file        = isinstance(resource, a.File)
			current        = self._effective(namespace, base, relative) if is_file else None

			for path, status in paths.items():
				index, event = sources[namespace, path]

				if is_file:
					affected = (
						path == old or path == current
						or (old is not None and old.startswith(path + os.sep))
						or (current is not None and current.startswith(path + os.sep))
					)
				elif relative is not None and event is not None:
					within = relative == '.' or event == relative or event.startswith(relative + os.sep)
					affected = False

					if within:
						key = (namespace, path)
						if key not in visibility:
							visibility[key] = self._visible(namespace, path, index, event)

						affected = visibility[key]
				else:
					affected = path == base or path.startswith(base + os.sep)

				if affected:
					name = os.path.relpath(event, relative) if event is not None and relative is not None else os.path.relpath(path, base)
					changed.setdefault(resource, {})[name.replace(os.sep, '/')] = status

			if is_file:
				if resource in changed:
					resource._invalidate()

				with self._observation_lock:
					entry = self._resources.get(resource)

					if entry is not None:
						entry['path'] = current

		for resource, notification in changed.items():
			resource.update(notification)

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Defer publication of a watched root across an asynchronous operation.
	# ----------------------------------------------------------------------
	@asynccontextmanager
	async def defer_changes(self, root):
		'''Buffer notifications for this physical watched root. Publish them on
		success; retain them after failure until a successful retry of the same
		root. Other roots continue normally. Does not drain active requests.'''
		root = os.path.realpath(root)

		async with self._defer_lock:
			with self._dispatch_lock:
				self._deferred_changes.setdefault(root, {})

			yield

			with self._dispatch_lock:
				paths = self._deferred_changes.pop(root)

				if paths:
					self._deliver_changes(root, paths)

	# Track a resource only while it has listeners; share its OS watchers.
	# ----------------------------------------------------------------------
	def observe(self, resource):
		if isinstance(resource, a.FilesystemResource):
			with self._observation_lock:
				if resource.is_subscribed():
					if resource not in self._resources:
						namespace      = resource._namespace_lib
						path           = resource.get_path()
						_, _, relative = self._source(namespace, path)

						self._resources[resource] = {
							'roots': self._roots_for(namespace, path, relative),
							'path' : self._effective(namespace, path, relative) if isinstance(resource, a.File) else None
						}

						try:
							self._reconcile()
						except BaseException:
							del self._resources[resource]
							self._reconcile()
							raise
				elif resource in self._resources:
					del self._resources[resource]
					self._reconcile()
		else:
			raise TypeError('Filesystem observation requires a FilesystemResource')
