# ==============================================================================
# FILESYSTEM SERVICE
# ==============================================================================
# Observe effective Almasi resources and invalidate cached namespace faces.
# ==============================================================================

import logging
import os
import threading

from watchfiles import watch

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

	# Describe a resource's namespace path without confusing its source owner.
	# --------------------------------------------------------------------------
	def _location(self, resource):
		namespace = resource._namespace_lib
		path      = resource.get_path()
		route     = resource.get_route()
		name      = resource.get_name()
		logical   = False
		parts     = ()

		if route == namespace.__name__ and path == os.path.realpath(namespace.__path__):
			logical = True
		elif route.startswith(namespace.__name__ + '.'):
			component = name if route.endswith('.' + name) else route.rsplit('.', 1)[-1]
			parent    = route[:-(len(component) + 1)]
			relative  = parent[len(namespace.__name__):].lstrip('.')
			parts     = tuple(relative.split('.')) if relative else ()
			matching  = component == name or component == os.path.splitext(name)[0]

			if not matching:
				matching = namespace.String.camel_to_snake(component) == os.path.splitext(name)[0]

			if matching:
				for layer in namespace.__instances__():
					expected = os.path.realpath(os.path.join(layer.__path__, *parts))
					if os.path.dirname(path) == expected:
						logical = True
						break

		return namespace, parts, component if route != namespace.__name__ else None, logical

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
				paths = {
					os.path.realpath(path) for change, path in changes
					if not os.path.basename(path).startswith('.almasi-')
				}

				if paths:
					self._changed_paths(root, paths)
		except Exception:
			logging.exception('Filesystem observer failed: %s', root)

	# Register one resource and reuse watchers already serving its roots.
	# --------------------------------------------------------------------------
	def _retain(self, resource):
		entry = self._resources.get(resource)

		if entry is None:
			roots = self._roots_for(resource)
			entry = {'references': 0, 'roots': roots, 'path': self._effective(resource)}
			self._resources[resource] = entry

			for root in roots:
				watcher = self._watchers.get(root)

				if watcher is None:
					stop    = threading.Event()
					thread  = threading.Thread(target=self._watch, args=(root, stop), daemon=True)
					watcher = {'stop': stop, 'thread': thread, 'references': 0}
					self._watchers[root] = watcher
					thread.start()

				watcher['references'] += 1

		entry['references'] += 1

	# Release the OS observer when no subscribed resources need its root.
	# --------------------------------------------------------------------------
	def _release(self, resource):
		entry = self._resources[resource]
		entry['references'] -= 1

		if entry['references'] == 0:
			del self._resources[resource]

			for root in entry['roots']:
				watcher = self._watchers[root]
				watcher['references'] -= 1

				if watcher['references'] == 0:
					watcher['stop'].set()
					del self._watchers[root]

	# Replace a resource scope while maintaining its watcher ownership.
	# --------------------------------------------------------------------------
	def _update_subscription(self, subscription, identifiers):
		resources = self._resources_in(identifiers)

		with self._subscription_lock:
			if not subscription._active:
				raise RuntimeError('Cannot update a canceled subscription')

			before = subscription._identifiers
			for resource in resources - before:
				self._retain(resource)

			super()._update_subscription(subscription, resources)

			for resource in before - resources:
				self._release(resource)

	# Release watchers through the same idempotent handle cancellation path.
	# --------------------------------------------------------------------------
	def _cancel_subscription(self, subscription):
		with self._subscription_lock:
			if subscription._active:
				resources = subscription._identifiers
				super()._cancel_subscription(subscription)

				for resource in resources:
					self._release(resource)

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

	# Check whether a directory's logical subtree contains this event.
	# --------------------------------------------------------------------------
	def _in_directory(self, resource, relative):
		namespace, parts, name, logical = self._location(resource)
		prefix = tuple(parts) + ((name,) if name is not None else ())
		path   = tuple(relative.split(os.sep))

		return len(path) >= len(prefix) and path[:len(prefix)] == prefix

	# Invalidate all affected namespace caches before delivering notifications.
	# --------------------------------------------------------------------------
	def _invalidate_path(self, namespace, path):
		layer_index, relative = self._event_source(namespace, path)

		if layer_index is not None:
			layer = tuple(namespace.__instances__())[layer_index]
			a.Directory(layer, os.path.dirname(path), layer.__name__)._invalidate_children(path)

	# Deliver only changes that affect the currently visible resource.
	# --------------------------------------------------------------------------
	def _changed_paths(self, root, paths):
		with self._subscription_lock:
			observed = tuple(
				(resource, entry['path'], entry['roots'])
				for resource, entry in self._resources.items()
			)

		changed = set()

		for path in paths:
			namespaces = {
				resource._namespace_lib for resource, old, roots in observed if root in roots
			}

			for namespace in namespaces:
				self._invalidate_path(namespace, path)

			for resource, old, roots in observed:
				if root in roots:
					namespace, parts, name, logical = self._location(resource)
					layer_index, relative = self._event_source(namespace, path)
					current = self._effective(resource)

					if isinstance(resource, a.File):
						affected = old != current or path == old or path == current
					elif logical and layer_index is not None and relative is not None:
						affected = self._in_directory(resource, relative) and self._is_visible_change(
							namespace, path, layer_index, relative
						)
					else:
						base = resource.get_path()
						affected = path == base or path.startswith(base + os.sep)

					if affected:
						if isinstance(resource, a.File):
							resource._invalidate()
						changed.add(resource)

					with self._subscription_lock:
						if resource in self._resources:
							self._resources[resource]['path'] = current

		if changed:
			self._dispatch(changed)

	# ==========================================================================
	# PUBLIC METHODS
	# ==========================================================================

	# Register interest in one or more resources with no eager watcher at import.
	# --------------------------------------------------------------------------
	def subscribe(self, identifiers=None, callback=None):
		resources = self._resources_in(identifiers)

		with self._subscription_lock:
			subscription = super().subscribe(resources, callback)

			try:
				for resource in resources:
					self._retain(resource)
			except BaseException:
				super()._cancel_subscription(subscription)
				raise

		return subscription
