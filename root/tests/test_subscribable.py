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
		class Source(a.Subscribable):
			pass

		return Source()

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
		handle   = source.subscribe({1}, received.append)

		def change_scope(changed):
			handle.update({2})

		source.subscribe(change_scope)
		source._dispatch({1})
		source._dispatch({2})

		assert received == [frozenset({1}), frozenset({2})]

	# Suppress pending callbacks canceled during an earlier callback.
	# ----------------------------------------------------------------------
	@classmethod
	def test_cancel_during_dispatch(cls):
		source   = cls._source()
		received = []
		handle   = source.subscribe(received.append)

		def cancel(changed):
			handle.cancel()

		source.subscribe(cancel)
		source._dispatch({1})
		source._dispatch({2})

		assert len(received) <= 1

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
