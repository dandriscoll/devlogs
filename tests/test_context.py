import pytest
from devlogs import context

def test_operation_context_sets_and_resets():
    with context.operation("opid", "web"):
        assert context.get_operation_id() == "opid"
        assert context.get_area() == "web"
    assert context.get_operation_id() is None
    assert context.get_area() is None

def test_set_area():
    context.set_area("jobs")
    assert context.get_area() == "jobs"
