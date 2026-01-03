# Indexing logic for log documents

def index_log_entry(client, index, doc):
	"""Index a log entry document."""
	return client.index(index=index, body=doc)
