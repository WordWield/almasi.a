# ==============================================================================
# TEST SUBSCRIBABLE
# ==============================================================================
# Verify shared subscription scopes, delivery, cancellation and concurrency.
# ==============================================================================

import threading

import a


class TestSubscribable(a.Tester):

	# ==========================================================================
	# PRIVATE METHODS
	# ==========================================================================

	# Use a new concrete service class to isolate each test's singleton.
	# ----------------------------------------------------------------------
	@classmethod
	def _source(cls):
		source = a.Subscribable()

		for subscription in tuple(source._subscriptions):
			subscription.cancel()

		return source

	# ==========================================================================
	# PUBLIC METHODS
	# ==========================================================================

	# Keep broad, selective and empty scopes distinct.
	# ----------------------------------------------------------------------
	@classmethod
	def test_broad_filtered_and_empty_subscriptions(cls):
		source  = cls._source()
		broad   = []
		narrow  = []
		empty   = []
		changes = {1, 2}

		source.subscribe(broad.append)
		source.subscribe({2, 3}, narrow.append)
		source.subscribe(set(), empty.append)
		source._dispatch(changes)
		source._dispatch(None)

		assert broad == [frozenset({1, 2}), None]
		assert narrow == [frozenset({2}), None]
		assert empty == [None]

	# Give each subscription its own handle, even for the same callback.
	# ----------------------------------------------------------------------
	@classmethod
	def test_independent_handles_and_idempotent_cancel(cls):
		source   = cls._source()
		received = []
		one      = source.subscribe({1}, received.append)
		two      = source.subscribe({2}, received.append)

		one.cancel()
		one.cancel()
		source._dispatch({1, 2})

		assert received == [frozenset({2})]
		assert two is not one

	# Snapshot mutable inputs and replace scope on the existing handle.
	# ----------------------------------------------------------------------
	@classmethod
	def test_scope_snapshots_and_update(cls):
		source      = cls._source()
		received    = []
		identifiers = {1}
		handle      = source.subscribe(identifiers, received.append)

		identifiers.add(2)
		source._dispatch({2})
		handle.update({2})
		source._dispatch({1, 2})

		assert received == [frozenset({2})]

		handle.cancel()

		try:
			handle.update({3})
		except RuntimeError:
			error = True
		else:
			error = False

		assert error

	# Preserve the start-of-batch scope when a callback changes another one.
	# ----------------------------------------------------------------------
	@classmethod
	def test_dispatch_scope_snapshot(cls):
		source   = cls._source()
		received = []
		handle   = None

		def change_scope(changed):
			handle.update({2})

		source.subscribe(change_scope)
		handle = source.subscribe({1}, received.append)
		source._dispatch({1})
		source._dispatch({2})

		assert received == [frozenset({1}), frozenset({2})]

	# Suppress pending callbacks canceled during an earlier callback.
	# ----------------------------------------------------------------------
	@classmethod
	def test_cancel_during_dispatch(cls):
		source   = cls._source()
		received = []
		handle   = None

		def cancel(changed):
			handle.cancel()

		source.subscribe(cancel)
		handle = source.subscribe(received.append)
		source._dispatch({1})
		source._dispatch({2})

		assert received == []

	# Isolate callback errors and allow reentrant registration.
	# ----------------------------------------------------------------------
	@classmethod
	def test_failure_and_reentrant_registration(cls):
		source   = cls._source()
		received = []

		def fail(changed):
			raise ValueError('test callback failure')

		def add(changed):
			source.subscribe({2}, received.append)

		source.subscribe(fail)
		source.subscribe({1}, add)
		source._dispatch({1})
		source._dispatch({2})

		assert frozenset({2}) in received

	# Source-specific payloads belong to each dispatch, including nested calls.
	# ----------------------------------------------------------------------
	@classmethod
	def test_stateless_dispatch_payload(cls):
		source   = cls._source()
		received = []

		def first(payload):
			received.append(('first', payload))
			source._dispatch({2}, lambda matching: {'two': 'deleted'})

		source.subscribe({1}, first)
		source.subscribe({2}, received.append)
		source._dispatch(
			{1, 2},
			lambda matching: {'one': 'created'} if 1 in matching else {'two': 'modified'}
		)

		assert received == [
			('first', {'one': 'created'}),
			{'two': 'deleted'},
			{'two': 'modified'}
		]

	# Concurrent producers deliver their own metadata without shared state.
	# ----------------------------------------------------------------------
	@classmethod
	def test_concurrent_dispatch_payloads(cls):
		source   = cls._source()
		barrier  = threading.Barrier(2)
		received = []

		def receive(payload):
			barrier.wait(timeout=2)
			received.append(payload)

		source.subscribe({1}, receive)
		workers = [
			threading.Thread(
				target = source._dispatch,
				args   = ({1}, lambda matched, event=event: {'event': event})
			)
			for event in ('created', 'deleted')
		]

		for worker in workers:
			worker.start()

		for worker in workers:
			worker.join(timeout=2)

		assert all(not worker.is_alive() for worker in workers)
		assert {entry['event'] for entry in received} == {'created', 'deleted'}

	# Cancellation never waits for an already running callback.
	# ----------------------------------------------------------------------
	@classmethod
	def test_nonblocking_cancel_of_running_callback(cls):
		source  = cls._source()
		started = threading.Event()
		release = threading.Event()
		calls   = []

		def callback(changed):
			calls.append(changed)
			started.set()
			release.wait(timeout=2)

		handle = source.subscribe(callback)
		worker = threading.Thread(target=source._dispatch, args=({1},))
		worker.start()

		try:
			assert started.wait(timeout=2)
			handle.cancel()
			source._dispatch({2})
		finally:
			release.set()
			worker.join(timeout=2)

		assert not worker.is_alive()
		assert calls == [frozenset({1})]

	# Multiple changed IDs notify each listener once with its intersection.
	# ----------------------------------------------------------------------
	@classmethod
	def test_indexed_overlap_and_broad_scope(cls):
		source   = cls._source()
		received = []
		source.subscribe({1, 2}, lambda ids: received.append(('first', ids)))
		source.subscribe({2, 3}, lambda ids: received.append(('second', ids)))
		source.subscribe(lambda ids: received.append(('broad', ids)))
		source.subscribe({8}, lambda ids: received.append(('other', ids)))
		source._dispatch(frozenset({1, 2, 3}))

		assert received == [
			('first', frozenset({1, 2})),
			('second', frozenset({2, 3})),
			('broad', frozenset({1, 2, 3})),
		]

	# Updating and canceling a subscription release old index entries.
	# ----------------------------------------------------------------------
	@classmethod
	def test_index_scope_changes_and_cleanup(cls):
		source   = cls._source()
		received = []
		handle   = source.subscribe({1, 2}, received.append)
		handle.update({3})
		assert 1 not in source._by_id and 2 not in source._by_id
		source._dispatch({1, 2, 3})
		assert received == [frozenset({3})]

		handle.update(None)
		source._dispatch({4})
		assert received[-1] == frozenset({4})
		handle.update(set())
		source._dispatch({4})
		source._dispatch(set())
		assert len(received) == 2

		handle.cancel()
		assert not source._by_id and not source._broad

	# Registration order survives cancel/update and new subscriptions.
	# ----------------------------------------------------------------------
	@classmethod
	def test_indexed_delivery_order(cls):
		source   = cls._source()
		received = []
		first    = source.subscribe({1}, lambda ids: received.append('first'))
		second   = source.subscribe({1}, lambda ids: received.append('second'))
		first.cancel()
		third    = source.subscribe({1}, lambda ids: received.append('third'))
		second.update({2})
		second.update({1})
		source._dispatch({1})

		assert received == ['second', 'third']
		third.cancel()

	# Reentrant update preserves old filters through the current batch.
	# ----------------------------------------------------------------------
	@classmethod
	def test_indexed_reentrant_update(cls):
		source   = cls._source()
		received = []
		handle   = None

		def update(ids):
			handle.update({3})

		source.subscribe({2}, update)
		handle = source.subscribe({2}, received.append)
		source._dispatch({2})
		source._dispatch({3})
		assert received == [frozenset({2}), frozenset({3})]

	# Large sparse and dense batches take different routes with equal semantics.
	# ----------------------------------------------------------------------
	@classmethod
	def test_indexed_sparse_and_dense_dispatch(cls):
		source   = cls._source()
		received = []
		handles  = [
			source.subscribe({index}, lambda ids, index=index: received.append((index, ids)))
			for index in range(100)
		]
		source._dispatch({27})
		assert received == [(27, frozenset({27}))]

		received.clear()
		for handle in handles:
			handle.update({5})

		source._dispatch({5, 27})
		assert len(received) == 100
		assert received == [(index, frozenset({5})) for index in range(100)]

	# Reject malformed registration values before creating a handle.
	# ----------------------------------------------------------------------
	@classmethod
	def test_contract_validation(cls):
		source = cls._source()

		for identifiers, callback in (([1], lambda changed: None), ({1}, None)):
			try:
				source.subscribe(identifiers, callback)
			except TypeError:
				error = True
			else:
				error = False

			assert error


if __name__ == '__main__':
	TestSubscribable.run()
