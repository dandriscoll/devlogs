import logging
from devlogs.handler import OpenSearchHandler

class DummyClient:
    def __init__(self):
        self.indexed = []
    def index(self, index, body):
        self.indexed.append((index, body))

def test_handler_emits_and_indexes(monkeypatch):
    dummy = DummyClient()
    handler = OpenSearchHandler(opensearch_client=dummy, index_name="test-index")
    logger = logging.getLogger("devlogs-test")
    logger.setLevel(logging.DEBUG)
    logger.handlers = [handler]
    logger.debug("hello world")
    assert dummy.indexed
