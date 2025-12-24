# Context management for operation_id and area

import contextvars
import uuid
from contextlib import contextmanager
from typing import Optional

_operation_id_var = contextvars.ContextVar("operation_id", default=None)
_parent_operation_id_var = contextvars.ContextVar("parent_operation_id", default=None)
_area_var = contextvars.ContextVar("area", default=None)
_rollup_default = True


def set_rollup_default(enabled: bool) -> None:
	"""Set the default rollup behavior for operation contexts."""
	global _rollup_default
	_rollup_default = bool(enabled)

def _rollup_operation(operation_id: str) -> None:
	try:
		from .config import load_config
		from .opensearch.client import get_opensearch_client
		from .rollup import rollup_operation
		cfg = load_config()
		client = get_opensearch_client()
		rollup_operation(client, cfg.index_logs, operation_id, refresh=True)
	except Exception as exc:
		print(f"[devlogs] Failed to roll up operation {operation_id}: {exc}")


@contextmanager
def operation(
	operation_id: Optional[str] = None,
	area: Optional[str] = None,
	rollup: Optional[bool] = None,
):
	"""Context manager to set operation_id and area for log context.

	When nested, the outer operation becomes the parent_operation_id.
	Rollup runs only for the outermost operation context.
	"""
	token_op = None
	token_parent = None
	token_area = None
	prev_operation_id = _operation_id_var.get()
	if operation_id is None:
		operation_id = str(uuid.uuid4())
	rollup_enabled = _rollup_default if rollup is None else rollup
	should_rollup = rollup_enabled and prev_operation_id is None
	try:
		token_op = _operation_id_var.set(operation_id)
		# If there was a previous operation, it becomes the parent
		if prev_operation_id is not None:
			token_parent = _parent_operation_id_var.set(prev_operation_id)
		if area is not None:
			token_area = _area_var.set(area)
		yield
	finally:
		if should_rollup and operation_id:
			_rollup_operation(operation_id)
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
