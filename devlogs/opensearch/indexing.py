# Indexing logic for log and operation documents

def index_log_entry(client, index, doc):
	"""Index a log entry document."""
	return client.index(index=index, body=doc)

def index_operation_doc(client, index, doc):
	"""Index a parent operation document."""
	return client.index(index=index, body=doc)
