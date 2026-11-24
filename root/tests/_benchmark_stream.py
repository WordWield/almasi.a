# ==============================================================================
# STREAM PERFORMANCE
# ==============================================================================
# Compare real file-backed streams using the same workload and runner.
# ==============================================================================

import runpy
import statistics
import sys
import time

import almasi


# Measure one case without retaining data between runs.
# ----------------------------------------------------------------------
def measure(stream_type, size, count, retention, operation):
	limit  = {'all': None, 'ring': size * 8 + 17, 'oversized': size // 4}[retention]
	stream = stream_type(max_bytes=limit)
	data   = b'x' * size

	if operation == 'read':
		for _ in range(10 if retention == 'ring' else 1):
			stream.write(data)

	started = time.perf_counter_ns()

	if operation == 'write':
		for _ in range(count):
			stream.write(data)
	else:
		position = limit - size // 2 if retention == 'ring' else stream.end_position - size

		for _ in range(count):
			assert len(stream.read(position, size)) == size

	elapsed = time.perf_counter_ns() - started

	return elapsed / count / 1000


# Alternate implementations to reduce systematic timing bias.
# ----------------------------------------------------------------------
def run():
	implementations = {'after': almasi.resources.Stream}

	if len(sys.argv) > 1:
		implementations = {'before': runpy.run_path(sys.argv[1])['Stream'], **implementations}

	print('Python', sys.version.split()[0])
	print('Operation | Block | Retention | ' + ' | '.join(implementations) + ' (us/op)')

	for size, count in ((256, 20000), (65536, 2000), (1048576, 200)):
		for retention in ('all', 'ring', 'oversized'):
			operations = ('write',) if retention == 'oversized' else ('write', 'read')

			for operation in operations:
				samples = {name: [] for name in implementations}

				for round_index in range(5):
					order = tuple(implementations) if round_index % 2 == 0 else tuple(reversed(implementations))

					for name in order:
						samples[name].append(measure(implementations[name], size, count, retention, operation))

				medians = [statistics.median(values) for values in samples.values()]
				print(f'{operation} | {size} | {retention} | ' + ' | '.join(f'{value:.3f}' for value in medians), flush=True)


if __name__ == '__main__':
	run()
