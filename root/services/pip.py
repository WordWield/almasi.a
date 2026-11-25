# ==============================================================================
# PIP SERVICE
# ==============================================================================
# PURPOSE:
# Maintain declared Python dependencies in the current interpreter environment.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: One requirements file, package operations and declaration updates.
# Delegates: Dependency resolution and environment changes to pip.
# ==============================================================================

import importlib
import json
import os
import re
import subprocess
import sys
import threading

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils        import canonicalize_name
from packaging.version      import Version

from almasi import a


class Pip(a.Singleton):

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Run pip in the interpreter that owns this service, without a shell.
	# ----------------------------------------------------------------------
	def _run(self, *arguments):
		try:
			process = subprocess.run(
				[sys.executable, '-m', 'pip', '--disable-pip-version-check', '--no-input', *arguments],
				cwd            = self._directory.get_path(),
				capture_output = True,
				text           = True,
				check          = True
			)
		except subprocess.CalledProcessError as error:
			for output in (error.stdout, error.stderr):
				if output and output.strip():
					error.add_note(output.strip())

			raise

		return process.stdout

	# Accept distribution names, not pip options or arbitrary requirement text.
	# ----------------------------------------------------------------------
	def _package_name(self, name):
		if isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?', name):
			result = canonicalize_name(name)
		else:
			raise ValueError(f'Invalid Python distribution name: {name!r}')

		return result

	# Construct an inclusive version range using standard Python versions.
	# ----------------------------------------------------------------------
	def _requirement(self, name, min_version, max_version):
		minimum = Version(min_version) if min_version is not None else None
		maximum = Version(max_version) if max_version is not None else None

		if minimum is None or maximum is None or minimum <= maximum:
			bounds = []

			if minimum is not None:
				bounds.append(f'>={minimum}')

			if maximum is not None:
				bounds.append(f'<={maximum}')

			result = self._package_name(name) + ','.join(bounds)
		else:
			raise ValueError('Minimum version exceeds maximum version')

		return result

	# Read the live file, not a cached namespace snapshot after a Git update.
	# ----------------------------------------------------------------------
	def _read(self):
		path = os.path.join(self._directory.get_path(), self._filename)

		if not os.path.islink(path) and os.path.isfile(path):
			with open(path, encoding='utf-8') as stream:
				result = stream.read()
		else:
			raise ValueError(f'Expected a regular requirements file: {path}')

		return result

	# Preserve unrelated declarations and replace matching simple package lines.
	# ----------------------------------------------------------------------
	def _edit(self, name, requirement):
		lines   = []
		matched = False

		for line in self._read().splitlines(keepends=True):
			declaration = re.split(r'\s+#', line, maxsplit=1)[0].strip()

			if declaration and not declaration.startswith('#'):
				try:
					parsed = Requirement(declaration)
				except InvalidRequirement as error:
					raise ValueError(f'Edit complex requirements file manually: {line.strip()}') from error
			else:
				parsed = None

			if parsed is not None and canonicalize_name(parsed.name) == name:
				if not parsed.extras and parsed.marker is None and parsed.url is None:
					if not matched and requirement is not None:
						lines.append(requirement + '\n')

					matched = True
				else:
					raise ValueError(f'Edit complex declaration manually: {line.strip()}')
			else:
				lines.append(line)

		if not matched and requirement is not None:
			if lines and not lines[-1].endswith('\n'):
				lines[-1] += '\n'

			lines.append(requirement + '\n')

		return ''.join(lines)

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Bind the entity's declaration and ensure its initial dependencies.
	# ----------------------------------------------------------------------
	def initialize(self, requirements_path: str) -> None:
		path            = os.path.abspath(requirements_path)
		self._directory = a.Directory(a, os.path.dirname(path), 'almasi.requirements')
		self._filename  = os.path.basename(path)
		self._lock      = threading.RLock()

		if self._filename.endswith('.txt') and not os.path.islink(path):
			self.sync()
		else:
			raise ValueError('Expected a regular requirements text file, not a symlink')

	# Ensure every declared requirement is installed; do not remove packages.
	# ----------------------------------------------------------------------
	def sync(self) -> None:
		'''Install the current requirements file without freezing the environment.'''
		with self._lock:
			path = os.path.join(self._directory.get_path(), self._filename)

			if not os.path.lexists(path):
				self._directory.write(self._filename, '')
			elif not os.path.islink(path) and os.path.isfile(path):
				self._run('install', '-r', path)
				importlib.invalidate_caches()
			else:
				raise ValueError(f'Expected a regular requirements file: {path}')

	# Install a distribution and publish its declaration only after success.
	# ----------------------------------------------------------------------
	def install(
		self,
		name        : str,
		min_version : str | None = None,
		max_version : str | None = None
	) -> None:
		'''Install a named distribution with optional inclusive version bounds.'''
		requirement = self._requirement(name, min_version, max_version)

		with self._lock:
			content = self._edit(self._package_name(name), requirement)
			self._run('install', requirement)
			importlib.invalidate_caches()
			self._directory.write(self._filename, content)

	# Remove a distribution from the environment and its direct declaration.
	# ----------------------------------------------------------------------
	def uninstall(self, name: str) -> None:
		'''Uninstall a distribution from the shared environment and this file.'''
		name = self._package_name(name)

		with self._lock:
			content = self._edit(name, None)
			self._run('uninstall', '-y', name)
			importlib.invalidate_caches()
			self._directory.write(self._filename, content)

	# Read installed distribution versions without touching the declaration.
	# ----------------------------------------------------------------------
	def list(self) -> dict[str, str]:
		'''Return pip's installed distribution names and versions.'''
		with self._lock:
			result = {item['name']: item['version'] for item in json.loads(self._run('list', '--format=json'))}

		return result

	# Return a separate environment snapshot without modifying requirements.
	# ----------------------------------------------------------------------
	def freeze(self) -> str:
		'''Return pip freeze output as requirements-compatible text.'''
		with self._lock:
			result = self._run('freeze')

		return result
