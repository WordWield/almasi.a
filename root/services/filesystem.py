# ==============================================================================
# FILESYSTEM SERVICE
# ==============================================================================
# Observe effective Almasi resources and invalidate cached namespace faces.
# ==============================================================================

import logging
import os
import threading

from watchfiles import Change, watch

import a


class Filesystem(a.Subscribable):

	# ==========================================================================
	# FRAMEWORK METHODS
	# ==========================================================================

	# Keep OS observers on the existing fork-local service singleton.
	# --------------------------------------------------------------------------
	def __new__(cls):
		instance = super().__new__(cls)

		if '_resources' not in instance.__dict__:
			instance._resources = {}
			instance._watchers  = {}

		return instance

	# ==========================================================================
	# PRIVATE METHODS
	# ==========================================================================

	# Validate that each subscription identifies concrete Almasi resources.
	# --------------------------------------------------------------------------
	def _resources_in(self, identifiers):
		resources = {identifiers} if isinstance(identifiers, a.Resource) else self._scope(identifiers)

		if resources is None or any(not isinstance(item, a.Resource) for item in resources):
			raise TypeError('Filesystem subscriptions require a set of Resources')

		return resources

	# Find the physical source layer and its path relative to that layer.
	# --------------------------------------------------------------------------
	def _source(self, namespace, path):
		index    = None
		relative = None

		for position, layer in enumerate(namespace.__instances__()):
			root = os.path.realpath(layer.__path__)

			if path == root or path.startswith(root + os.sep):
				index    = position
				relative = os.path.relpath(path, root)
				break

		return index, relative

	# Use Almasi's existing resolver for effective inherited resources.
	# --------------------------------------------------------------------------
	def _resolve(self, namespace, relative):
		parent = os.path.dirname(relative)
		route  = namespace.__name__ + ('.' + parent.replace(os.sep, '.') if parent else '')
		face   = a.Directory(namespace, os.path.join(namespace.__path__, parent), route)
		found  = face.__resolve__(os.path.basename(relative))

		return found.get_path() if found is not None else None

	# Keep the resolved source path to detect overridden files and removals.
	# --------------------------------------------------------------------------
	def _effective(self, resource):
		_, relative = self._source(resource._namespace_lib, resource.get_path())

		if relative is not None and relative != '.':
			path = self._resolve(resource._namespace_lib, relative)
		else:
			path = resource.get_path() if os.path.exists(resource.get_path()) else None

		return path

	# Observe all inherited roots or the parent of an external resource.
	# --------------------------------------------------------------------------
	def _roots_for(self, resource):
		namespace, path = resource._namespace_lib, resource.get_path()
		_, relative     = self._source(namespace, path)

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

	# Derive OS watchers from Subscribable's existing active identifier index.
	# No second reference-counting system is needed for registered resources.
	# --------------------------------------------------------------------------
	def _reconcile(self):
		active = set(self._by_id)

		for resource in active - self._resources.keys():
			self._resources[resource] = {
				'roots': self._roots_for(resource),
				'path' : self._effective(resource) if isinstance(resource, a.File) else None
			}

		for resource in self._resources.keys() - active:
			del self._resources[resource]

		roots = {root for entry in self._resources.values() for root in entry['roots']}

		for root in roots - self._watchers.keys():
			stop   = threading.Event()
			thread = threading.Thread(target=self._watch, args=(root, stop), daemon=True)
			thread.start()
			self._watchers[root] = {'stop': stop, 'thread': thread}

		for root in self._watchers.keys() - roots:
			self._watchers.pop(root)['stop'].set()

	# Replace the scope in the common registry, then reconcile OS observers.
	# --------------------------------------------------------------------------
	def _update_subscription(self, subscription, identifiers):
		resources = self._resources_in(identifiers)

		with self._subscription_lock:
			before = subscription._identifiers
			super()._update_subscription(subscription, resources)

			try:
				self._reconcile()
			except BaseException:
				super()._update_subscription(subscription, before)
				self._reconcile()
				raise

	# The common registry already knows whether the subscription is active.
	# --------------------------------------------------------------------------
	def _cancel_subscription(self, subscription):
		with self._subscription_lock:
			super()._cancel_subscription(subscription)
			self._reconcile()

	# Ignore shadowed changes, while notifying when an override disappears.
	# --------------------------------------------------------------------------
	def _visible(self, namespace, path, index, relative):
		effective = self._resolve(namespace, relative)
		visible   = effective is None or effective == path

		if not visible:
			effective_index, _ = self._source(namespace, effective)
			visible = effective_index is not None and index < effective_index

		return visible

	# Map physical changes to subscribed resources and invalidate before dispatch.
	# --------------------------------------------------------------------------
	def _changed_paths(self, root, paths):
		with self._subscription_lock:
			observed = tuple(
				(resource, entry['path'])
				for resource, entry in self._resources.items()
				if root in entry['roots']
			)

		namespaces = {resource._namespace_lib for resource, old in observed}
		sources    = {}
		visibility = {}

		for path in paths:
			for namespace in namespaces:
				index, relative = self._source(namespace, path)
				layer = tuple(namespace.__instances__())[index] if index is not None else namespace
				a.Directory(layer, os.path.dirname(path), layer.__name__)._invalidate_children(path)
				sources[namespace, path] = (index, relative)

		changed = {}

		for resource, old in observed:
			namespace   = resource._namespace_lib
			base        = resource.get_path()
			_, relative = self._source(namespace, base)
			is_file     = isinstance(resource, a.File)
			current     = self._effective(resource) if is_file else None

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
					name = event if event is not None else os.path.relpath(path, os.path.dirname(base))
					changed.setdefault(resource, {})[name.replace(os.sep, '/')] = status

			if resource in changed and is_file:
				resource._invalidate()

			if is_file:
				with self._subscription_lock:
					entry = self._resources.get(resource)

					if entry is not None:
						entry['path'] = current

		if changed:
			self._dispatch(changed)

	# Match resource changes and build subscriber-specific event dictionaries.
	# Keep each batch local for nested and concurrent notifications.
	# --------------------------------------------------------------------------
	def _matches_generator(self, changed):
		for subscription, identifiers in self._snapshot:
			matching = changed.keys() & identifiers

			if matching:
				resources = {}

				for resource in matching:
					resources.update(changed[resource])

				yield subscription, resources

	# ==========================================================================
	# PUBLIC METHODS
	# ==========================================================================

	# Register interest in one or more resources with no eager watcher at import.
	# --------------------------------------------------------------------------
	def subscribe(self, identifiers=None, callback=None):
		resources = self._resources_in(identifiers)

		if not callable(callback):
			raise TypeError('Subscription callback must be callable')

		with self._subscription_lock:
			subscription = super().subscribe(resources, callback)

			try:
				self._reconcile()
			except BaseException:
				super()._cancel_subscription(subscription)
				self._reconcile()
				raise

		return subscription
