# ==============================================================================
# ANNOTATION
# ==============================================================================
# PURPOSE:
# Interpret Python type declarations, check values and provide explicit casts.
#
# RESPONSIBILITY BOUNDARIES:
# Owns: Python annotation structure, identity and value semantics.
# Delegates: Specialized type source expressions to descendants.
# ==============================================================================

import math
import types
import typing as t

from almasi import a


class Annotation(a.Module):

	# ======================================================================
	# FRAMEWORK METHODS
	# ======================================================================

	# Interpret the declared Python type without depending on a storage runtime.
	# ----------------------------------------------------------------------
	def __init__(self, annotation):
		super().__init__()

		if isinstance(annotation, Annotation):
			annotation = annotation.annotation
		elif isinstance(annotation, str):
			annotation = self._resolve_source(annotation)

		annotation = self._normalize(annotation)
		origin     = t.get_origin(annotation) or annotation

		self.is_function = annotation in (
			types.FunctionType,
			types.BuiltinFunctionType,
			types.MethodType,
			types.BuiltinMethodType,
		)

		self.annotation      = annotation
		self.origin          = origin
		self.args            = t.get_args(annotation)
		self.is_none         = annotation in (None, type(None))
		self.options         = self._get_options()
		self.is_module       = isinstance(annotation, a.Module)
		self.is_union        = bool(self.options)
		self.is_optional     = any(option.is_none for option in self.options)
		self.is_list         = origin is list
		self.is_dict         = origin is dict
		self.is_set          = origin is set
		self.is_tuple        = origin is tuple
		self.is_bool         = origin is bool
		self.is_container    = origin in (list, dict, set, tuple)
		self.is_atomic       = origin not in (list, dict, set, tuple)
		self.is_class        = isinstance(annotation, type) and not self.is_atomic and not self.is_container
		self.is_data         = self.is_atomic or self.is_container
		self.is_simple       = not self.args and not self.is_union
		self.key, self.value = self._get_key_value()
		self.is_homogenous   = self._get_is_homogenous()
		self.id              = self._get_id()

		self._validate()

	# Returns 'list[dict[str,int]]' - like string
	# ----------------------------------------------------------------------
	def __str__(self):
		text = None

		if self.is_none:
			text = 'None'
		elif self.is_union:
			text = '|'.join(sorted(str(option) for option in self.options))
		elif self.args:
			args = ','.join(str(type(self)(arg)) for arg in self.args)
			text = f'{self.origin.__name__}[{args}]'
		elif hasattr(self.annotation, '__name__'):
			text = self.annotation.__name__
		else:
			text = str(self.annotation)

		return text

	# Preserve the readable type notation.
	# ----------------------------------------------------------------------
	def __repr__(self):
		return str(self)

	# Preserve the established deterministic identity hash.
	# ----------------------------------------------------------------------
	def __hash__(self):
		return a.String.hash(self.id, 15)

	# Compare the canonical notation within the same annotation family.
	# ----------------------------------------------------------------------
	def __eq__(self, other):
		return isinstance(other, type(self)) and self.id == other.id

	# ======================================================================
	# PRIVATE METHODS
	# ======================================================================

	# Resolve trusted source expressions in Core's Python namespace.
	# ----------------------------------------------------------------------
	@staticmethod
	def _resolve_source(source):
		return eval(source)

	# Render a concrete Python type without imposing a persistent address.
	# ----------------------------------------------------------------------
	def _get_type_source(self):
		return self.annotation.__name__

	# Preserve ordinary aliases while resolving nested type declarations.
	# ----------------------------------------------------------------------
	@classmethod
	def _normalize(cls, annotation):
		origin = t.get_origin(annotation)
		args   = t.get_args(annotation)
		result = annotation

		if origin in (types.UnionType, t.Union):
			parts  = tuple(cls._normalize(arg) for arg in args)
			result = parts[0]

			for part in parts[1:]:
				result = result | part
		elif origin is t.Annotated:
			result = t.Annotated[cls._normalize(args[0]), *args[1:]]
		elif origin is t.Literal:
			result = annotation
		elif origin is not None:
			if args:
				result = origin[tuple(cls._normalize(arg) for arg in args)]
			elif not isinstance(annotation, types.GenericAlias):
				result = origin

		return result

	# Infer a union from the actual element types of a nonempty container.
	# ----------------------------------------------------------------------
	@classmethod
	def _join(cls, items):
		joined      = None
		annotations = sorted({cls.annotate(item).annotation for item in items}, key=repr)

		for annotation in annotations:
			joined = annotation if joined is None else joined | annotation

		return joined

	# Distinguish variable-length, fixed-length and untyped tuple declarations.
	# ----------------------------------------------------------------------
	def _matches_tuple(self, value):
		result = isinstance(value, tuple)

		if result and self.annotation is not tuple:
			if len(self.args) == 2 and self.args[1] is Ellipsis:
				annotation = type(self)(self.args[0])
				result     = all(annotation.matches(item) for item in value)
			else:
				result = len(value) == len(self.args) and all(
					type(self)(arg).matches(item) for item, arg in zip(value, self.args)
				)

		return result

	# Get union options
	# ----------------------------------------------------------------------
	def _get_options(self):
		options    = set()
		origin     = t.get_origin(self.annotation)
		union_type = getattr(types, 'UnionType', None)

		if origin in (t.Union, union_type):
			for arg in t.get_args(self.annotation):
				option = type(self)(arg)

				if option.is_union:
					for nested in option.options:
						options.add(nested)
				else:
					options.add(option)

		return options

	# Get key, value annotations
	# ----------------------------------------------------------------------
	def _get_key_value(self):
		key   = None
		value = None
		args  = t.get_args(self.annotation)

		if self.is_list:
			if len(args) not in (0, 1):
				raise TypeError(f'Invalid list annotation: `{self.annotation}`')

			key = type(self)(int)
			if len(args) == 1:
				value = type(self)(args[0])

		elif self.is_dict:
			if len(args) not in (0, 2):
				raise TypeError(f'Invalid dict annotation: `{self.annotation}`')

			if len(args) == 2:
				key   = type(self)(args[0])
				value = type(self)(args[1])

		return key, value

	# Get homogenous flag
	# ----------------------------------------------------------------------
	def _get_is_homogenous(self):
		h = True

		if   self.is_union                                           : h = False
		elif self.key   is not None and not self.key.is_homogenous   : h = False
		elif self.value is not None and not self.value.is_homogenous : h = False

		return h

	# Get canonical annotation id
	# ----------------------------------------------------------------------
	def _get_id(self):
		id = None

		if self.is_none:
			id = 'None'
		elif self.is_union:
			id = ' | '.join(sorted([option.id for option in self.options]))
		elif self.is_list:
			id = 'list' if self.value is None else f'list[{self.value.id}]'
		elif self.is_dict:
			id = 'dict' if self.key is None else f'dict[{self.key.id}, {self.value.id}]'
		else:
			id = self._get_origin_name()

		return id

	# Get readable origin name
	# ----------------------------------------------------------------------
	def _get_origin_name(self):
		name = None

		if self.origin is None                : name = 'None'
		elif hasattr(self.origin, '__name__') : name = self.origin.__name__
		else                                  : name = str(self.origin)

		return name

	# Validate tree invariants
	# ----------------------------------------------------------------------
	def _validate(self):
		for option in self.options:
			if not isinstance(option, type(self)):
				raise TypeError(f'Option must be `Annotation`, got `{type(option)}`')

		if self.key is not None and not isinstance(self.key, type(self)):
			raise TypeError(f'Key must be `Annotation`, got `{type(self.key)}`')

		if self.value is not None and not isinstance(self.value, type(self)):
			raise TypeError(f'Value must be `Annotation`, got `{type(self.value)}`')

	# Validate JSON number
	# ----------------------------------------------------------------------
	@classmethod
	def _validate_json_value(cls, value):
		if isinstance(value, float):
			if math.isnan(value) or math.isinf(value):
				raise ValueError(f'Invalid JSON number: `{value}`')

	# ======================================================================
	# PUBLIC METHODS
	# ======================================================================

	# Render a persistent expression without changing display or identity.
	# ----------------------------------------------------------------------
	def to_source(self):
		if self.annotation is None:
			result = 'None'
		elif self.is_none:
			result = 'type(None)'
		elif self.is_union:
			result = '(' + ' | '.join(sorted(type(self)(arg).to_source() for arg in self.args)) + ')'
		elif self.args:
			args   = ', '.join(type(self)(arg).to_source() for arg in self.args)
			result = f'{self.origin.__name__}[{args}]'
		elif self.annotation is Ellipsis:
			result = '...'
		elif self.annotation is t.Any:
			result = 't.Any'
		elif self.is_function:
			result = next(
				'types.' + name
				for name in ('FunctionType', 'BuiltinFunctionType', 'MethodType', 'BuiltinMethodType')
				if getattr(types, name) is self.annotation
			)
		else:
			result = self._get_type_source()

		return result

	# Recognize supported type declarations without constructing an annotation.
	# ----------------------------------------------------------------------
	@classmethod
	def is_annotation(cls, notation):
		return (
			isinstance(notation, type) or
			isinstance(notation, types.GenericAlias) or
			isinstance(notation, types.UnionType)
		)

	# Derive value annotation
	# ----------------------------------------------------------------------
	@classmethod
	def annotate(cls, value):

		annotation = None

		if isinstance(value, cls):
			annotation = value.annotation
		elif value is None:
			annotation = None
		elif isinstance(value, list):
			annotation = list if len(value) == 0 else list[cls._join(value)]
		elif isinstance(value, dict):
			annotation = dict if len(value) == 0 else dict[
				cls._join(value.keys()),
				cls._join(value.values()),
			]
		else:
			cls._validate_json_value(value)
			annotation = type(value)

		return cls(annotation)

	# Check a value without converting it or consuming a resource.
	# ----------------------------------------------------------------------
	def matches(self, value):
		origin = self.origin
		args   = self.args

		if self.annotation is t.Any:
			result = True
		elif self.is_none:
			result = value is None
		elif self.is_union:
			result = any(type(self)(arg).matches(value) for arg in args)
		elif origin is t.Annotated:
			result = type(self)(args[0]).matches(value)
		elif origin is t.Literal:
			result = any(type(value) is type(item) and value == item for item in args)
		elif self.is_list:
			result = isinstance(value, list) and (
				self.value is None or all(self.value.matches(item) for item in value)
			)
		elif self.is_dict:
			result = isinstance(value, dict) and (
				self.key is None or all(
					self.key.matches(key) and self.value.matches(item)
					for key, item in value.items()
				)
			)
		elif origin in (set, frozenset):
			result = isinstance(value, origin)

			if result and args:
				annotation = type(self)(args[0])
				result     = all(annotation.matches(item) for item in value)
		elif self.is_tuple:
			result = self._matches_tuple(value)
		elif origin is a.Resource:
			result = isinstance(value, origin)
		elif isinstance(self.annotation, type) and not args:
			result = isinstance(value, self.annotation)
		else:
			raise TypeError(f'Unsupported strict annotation: {self.annotation!r}')

		return result

	# Cast value to this annotation
	# ----------------------------------------------------------------------
	def cast(self, value):
		result = None

		if self.is_none:
			if value is not None:
				raise TypeError(f'Expected `None`, got `{type(value)}`')
			result = None

		elif self.is_union:
			error = None
			for option in sorted(self.options, key=lambda item: item.id):
				try:
					result = option.cast(value)
					error = None
					break
				except Exception as e:
					error = e
			if error is not None:
				raise TypeError(f'Value `{value}` does not match annotation `{self}`')

		elif self.is_list:
			if not isinstance(value, list):
				raise TypeError(f'Expected `list`, got `{type(value)}`')
			if self.value is None:
				result = list(value)
			else:
				result = [self.value.cast(item) for item in value]

		elif self.is_dict:
			if not isinstance(value, dict):
				raise TypeError(f'Expected `dict`, got `{type(value)}`')
			if self.key is None or self.value is None:
				result = dict(value)
			else:
				result = {}
				for k, v in value.items():
					result[self.key.cast(k)] = self.value.cast(v)

		elif self.is_bool:
			if value in (True, 'True', 1, '1'):
				result = True
			elif value in (False, 'False', 0, '0'):
				result = False
			else:
				raise TypeError(f'Expected `bool`, got `{value}`')

		else:
			if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
				raise ValueError(f'Invalid JSON number: `{value}`')
			result = self.origin(value)

		return result
