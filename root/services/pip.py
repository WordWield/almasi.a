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

from packaging.utils   import canonicalize_name
from packaging.version import Version

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

	# Read the current declaration after external changes.
	# ----------------------------------------------------------------------
	def _load(self):
		with open(self._path, 'r', encoding='utf-8') as file:
			self.requirements = file.read().splitlines()

	# Append one direct requirement.
	# ----------------------------------------------------------------------
	def _add_line(self, line):
		self.requirements.append(line)

	# Remove matching distribution names, not longer names sharing a prefix.
	# ----------------------------------------------------------------------
	def _remove_line(self, prefix):
		self.requirements = [
			line for line in self.requirements
			if canonicalize_name(re.split(r'[\s<>=!~;\[@]', line.lstrip(), maxsplit=1)[0]) != prefix
		]

	# Publish the declaration through the existing atomic file operation.
	# ----------------------------------------------------------------------
	def _save(self):
		content = '\n'.join(self.requirements)

		if self.requirements:
			content += '\n'

		self._directory.write(os.path.basename(self._path), content)

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Bind the entity's declaration and ensure its initial dependencies.
	# ----------------------------------------------------------------------
	def initialize(self, requirements_path: str) -> None:
		self._path      = os.path.abspath(requirements_path)
		self._directory = a.Directory(a, os.path.dirname(self._path), 'almasi.requirements')
		self._lock      = threading.RLock()

		if self._path.endswith('.txt') and not os.path.islink(self._path):
			self.sync()
		else:
			raise ValueError('Expected a regular requirements text file, not a symlink')

	# Ensure every declared requirement is installed; do not remove packages.
	# ----------------------------------------------------------------------
	def sync(self) -> None:
		'''Install the current requirements file without freezing the environment.'''
		with self._lock:
			if not os.path.lexists(self._path):
				self.requirements = []
				self._save()
			elif not os.path.islink(self._path) and os.path.isfile(self._path):
				self._load()
				self._run('install', '-r', self._path)
				importlib.invalidate_caches()
			else:
				raise ValueError(f'Expected a regular requirements file: {self._path}')

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
			self._load()
			self._run('install', requirement)
			importlib.invalidate_caches()
			self._remove_line(self._package_name(name))
			self._add_line(requirement)
			self._save()

	# Remove a distribution from the environment and its direct declaration.
	# ----------------------------------------------------------------------
	def uninstall(self, name: str) -> None:
		'''Uninstall a distribution from the shared environment and this file.'''
		name = self._package_name(name)

		with self._lock:
			self._load()
			self._run('uninstall', '-y', name)
			importlib.invalidate_caches()
			self._remove_line(name)
			self._save()

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
