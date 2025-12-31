# Context management for operation_id and area

import contextvars
import uuid
from contextlib import contextmanager
from typing import Optional

_operation_id_var = contextvars.ContextVar("operation_id", default=None)
_parent_operation_id_var = contextvars.ContextVar("parent_operation_id", default=None)
_area_var = contextvars.ContextVar("area", default=None)


@contextmanager
def operation(
	operation_id: Optional[str] = None,
	area: Optional[str] = None,
):
	"""Context manager to set operation_id and area for log context.

	When nested, the outer operation becomes the parent_operation_id.
	"""
	token_op = None
	token_parent = None
	token_area = None
	prev_operation_id = _operation_id_var.get()
	if operation_id is None:
		operation_id = str(uuid.uuid4())
	try:
		token_op = _operation_id_var.set(operation_id)
		# If there was a previous operation, it becomes the parent
		if prev_operation_id is not None:
			token_parent = _parent_operation_id_var.set(prev_operation_id)
		if area is not None:
			token_area = _area_var.set(area)
		yield
	finally:
		if token_op:
			_operation_id_var.reset(token_op)
		if token_parent:
			_parent_operation_id_var.reset(token_parent)
		if token_area:
			_area_var.reset(token_area)

def set_area(area: str):
	_area_var.set(area)

def get_area() -> Optional[str]:
	return _area_var.get()

def get_operation_id() -> Optional[str]:
	return _operation_id_var.get()

def get_parent_operation_id() -> Optional[str]:
	return _parent_operation_id_var.get()
