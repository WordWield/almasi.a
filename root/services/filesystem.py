# ==============================================================================
# FILESYSTEM SERVICE
# ==============================================================================
# Observe effective Almasi resources and invalidate cached namespace faces.
# ==============================================================================

import logging
import os
import threading

from contextvars import ContextVar

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
			instance._events    = ContextVar('filesystem_events', default={})

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

	# Separate a resource's physical source from its observed logical route.
	# --------------------------------------------------------------------------
	def _location(self, resource):
		namespace = resource._namespace_lib
		path      = resource.get_path()
		route     = resource.get_route()
		name      = resource.get_name()
		parts     = ()
		component = None
		logical   = route == namespace.__name__ and path == os.path.realpath(namespace.__path__)

		if route.startswith(namespace.__name__ + '.'):
			parts     = tuple(route[len(namespace.__name__) + 1:].split('.'))
			component = parts[-1]
			parts     = parts[:-1]
			stem      = os.path.splitext(name)[0]
			matching  = component in (name, stem) or namespace.String.camel_to_snake(component) == stem

			if matching:
				logical = any(
					os.path.dirname(path) == os.path.realpath(os.path.join(layer.__path__, *parts))
					for layer in namespace.__instances__()
				)

		return namespace, parts, component, logical

	# Resolve the currently visible carrier, using Almasi's own namespace rules.
	# --------------------------------------------------------------------------
	def _effective(self, resource):
		namespace, parts, name, logical = self._location(resource)
		path = resource.get_path() if os.path.exists(resource.get_path()) else None

		if logical and name is not None:
			parent = namespace.__name__ + ('.' + '.'.join(parts) if parts else '')
			face   = a.Directory(namespace, os.path.join(namespace.__path__, *parts), parent)
			found  = face.__resolve__(name)
			path   = found.get_path() if found is not None else None

		return path

	# Watch each library source root, including roots where overrides may appear.
	# --------------------------------------------------------------------------
	def _roots_for(self, resource):
		namespace, parts, name, logical = self._location(resource)
		roots = set()

		if logical:
			roots = {os.path.realpath(layer.__path__) for layer in namespace.__instances__()}
		else:
			path = resource.get_path()
			roots = {os.path.dirname(path)}

		return {path for path in roots if os.path.isdir(path)}

	# Run one recursive watcher for each physical root needed by subscribers.
	# --------------------------------------------------------------------------
	def _watch(self, root, stop):
		try:
			for changes in watch(root, stop_event=stop, debounce=100, step=50, rust_timeout=500):
				paths = self._changes(changes)

				if paths:
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

	# Locate an event's source layer and logical path in the observed namespace.
	# --------------------------------------------------------------------------
	def _event_source(self, namespace, path):
		layer_index = None
		relative    = None

		for index, layer in enumerate(namespace.__instances__()):
			root = os.path.realpath(layer.__path__)

			if os.path.commonpath([root, path]) == root:
				layer_index = index
				relative    = os.path.relpath(path, root)
				break

		return layer_index, relative

	# Resolve one changed child through the effective inherited namespace.
	# --------------------------------------------------------------------------
	def _visible_child(self, namespace, relative):
		parts    = relative.split(os.sep)
		parent   = namespace.__name__ + ('.' + '.'.join(parts[:-1]) if len(parts) > 1 else '')
		location = os.path.join(namespace.__path__, *parts[:-1])
		face     = a.Directory(namespace, location, parent)
		child    = face.__resolve__(parts[-1])

		return child.get_path() if child is not None else None

	# Reject lower-priority physical changes masked by the effective namespace.
	# --------------------------------------------------------------------------
	def _is_visible_change(self, namespace, path, layer_index, relative):
		effective = self._visible_child(namespace, relative)
		visible   = effective is None or effective == path

		if not visible:
			effective_layer, other = self._event_source(namespace, effective)
			visible = effective_layer is not None and layer_index < effective_layer

		return visible

	# Invalidate affected carrier caches once per physical path and namespace.
	# --------------------------------------------------------------------------
	def _invalidate_path(self, namespace, path, layer_index):
		layer = tuple(namespace.__instances__())[layer_index] if layer_index is not None else namespace
		a.Directory(layer, os.path.dirname(path), layer.__name__)._invalidate_children(path)

	# Report logical library paths or paths relative to the subscribed carrier.
	# --------------------------------------------------------------------------
	def _event_name(self, resource, path, relative):
		name = relative if relative is not None else os.path.relpath(path, os.path.dirname(resource.get_path()))

		return name.replace(os.sep, '/')

	# Resolve source layers once per changed path, and effective files once per
	# subscribed resource. Keep notifications separate from cache invalidation.
	# --------------------------------------------------------------------------
	def _changed_paths(self, root, paths):
		with self._subscription_lock:
			observed = tuple(
				(resource, entry['path'], self._location(resource))
				for resource, entry in self._resources.items()
				if root in entry['roots']
			)

		namespaces = {location[0] for resource, old, location in observed}
		sources    = {}

		for path in paths:
			mapping = {}

			for namespace in namespaces:
				index, relative = self._event_source(namespace, path)
				self._invalidate_path(namespace, path, index)
				mapping[namespace] = (index, relative)

			sources[path] = mapping

		changed    = {}
		visibility = {}

		for resource, old, location in observed:
			namespace, parts, name, logical = location
			is_file = isinstance(resource, a.File)
			current = self._effective(resource) if is_file else None
			base    = resource.get_path()
			prefix  = os.sep.join(parts + ((name,) if name is not None else ()))

			for path, status in paths.items():
				index, relative = sources[path][namespace]

				if is_file:
					affected = (
						path == old or path == current
						or (old is not None and old.startswith(path + os.sep))
						or (current is not None and current.startswith(path + os.sep))
					)
				elif logical and index is not None and relative is not None:
					within = not prefix or relative == prefix or relative.startswith(prefix + os.sep)
					affected = False

					if within:
						key = (namespace, path)
						if key not in visibility:
							visibility[key] = self._is_visible_change(namespace, path, index, relative)

						affected = visibility[key]
				else:
					affected = path == base or path.startswith(base + os.sep)

				if affected:
					changed.setdefault(resource, {})[self._event_name(resource, path, relative)] = status

			if resource in changed and is_file:
				resource._invalidate()

			if is_file:
				with self._subscription_lock:
					entry = self._resources.get(resource)

					if entry is not None:
						entry['path'] = current

		if changed:
			token = self._events.set(changed)

			try:
				self._dispatch(set(changed))
			finally:
				self._events.reset(token)

	# ==========================================================================
	# PUBLIC METHODS
	# ==========================================================================

	# Reuse Subscribable dispatch, enriching filesystem invalidations with paths.
	# --------------------------------------------------------------------------
	def _notify(self, callback, matched):
		events  = self._events.get()
		changes = {}

		for resource in matched:
			changes.update(events.get(resource, {}))

		callback(changes)

	# Register interest in one or more resources with no eager watcher at import.
	# --------------------------------------------------------------------------
	def subscribe(self, identifiers=None, callback=None):
		resources = self._resources_in(identifiers)

		if not callable(callback):
			raise TypeError('Subscription callback must be callable')

		def deliver(matched):
			self._notify(callback, matched)

		with self._subscription_lock:
			subscription = super().subscribe(resources, deliver)

			try:
				self._reconcile()
			except BaseException:
				super()._cancel_subscription(subscription)
				self._reconcile()
				raise

		return subscription
