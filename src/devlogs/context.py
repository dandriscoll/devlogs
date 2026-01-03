# Context management for operation_id and area

import contextvars
import uuid
from contextlib import contextmanager
from typing import Optional

_operation_id_var = contextvars.ContextVar("operation_id", default=None)
_area_var = contextvars.ContextVar("area", default=None)


@contextmanager
def operation(
	operation_id: Optional[str] = None,
	area: Optional[str] = None,
):
	"""Context manager to set operation_id and area for log context.
	"""
	token_op = None
	token_area = None
	if operation_id is None:
		operation_id = str(uuid.uuid4())
	try:
		token_op = _operation_id_var.set(operation_id)
		if area is not None:
			token_area = _area_var.set(area)
		yield
	finally:
		if token_op:
			_operation_id_var.reset(token_op)
		if token_area:
			_area_var.reset(token_area)

def set_area(area: str):
	_area_var.set(area)

def get_area() -> Optional[str]:
	return _area_var.get()

def get_operation_id() -> Optional[str]:
	return _operation_id_var.get()
