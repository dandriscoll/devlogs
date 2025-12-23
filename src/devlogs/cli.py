import signal
import sys

# Handle Ctrl+C gracefully before any other imports
signal.signal(signal.SIGINT, lambda *_: sys.exit(130))

import time
import typer

from .config import load_config
from .opensearch.client import get_opensearch_client
from .opensearch.mappings import LOG_INDEX_TEMPLATE
from .opensearch.queries import tail_logs

app = typer.Typer()


@app.command()
def init():
	"""Initialize OpenSearch indices and templates (idempotent)."""
	cfg = load_config()
	client = get_opensearch_client()
	# Create or update index templates
	client.indices.put_index_template(name="devlogs-template", body=LOG_INDEX_TEMPLATE)
	# Create initial indices if not exist
	if not client.indices.exists(index=cfg.index_logs):
		client.indices.create(index=cfg.index_logs)
	typer.echo("OpenSearch indices and templates initialized.")


@app.command()
def tail(
	operation_id: str = typer.Option(None, "--operation", "-o"),
	area: str = typer.Option(None, "--area"),
	level: str = typer.Option(None, "--level"),
	since: str = typer.Option(None, "--since"),
	limit: int = typer.Option(20, "--limit"),
	follow: bool = typer.Option(False, "--follow"),
):
	"""Tail logs for a given area/operation."""
	cfg = load_config()
	client = get_opensearch_client()
	search_after = None
	while True:
		docs, search_after = tail_logs(
			client,
			cfg.index_logs,
			operation_id=operation_id,
			area=area,
			level=level,
			since=since,
			limit=limit,
			search_after=search_after,
		)
		for doc in docs:
			timestamp = doc.get("timestamp") or ""
			entry_level = doc.get("level") or ""
			entry_area = doc.get("area") or ""
			entry_operation = doc.get("operation_id") or ""
			message = doc.get("message") or ""
			typer.echo(f"{timestamp} {entry_level} {entry_area} {entry_operation} {message}")
		if not follow:
			break
		time.sleep(2)


@app.command()
def search(q: str = "", area: str = "web"):
	"""Search logs for a query (stub)."""
	typer.echo(f"[stub] Searching logs for area: {area}, query='{q}'")

def main():
	if len(sys.argv) == 1:
		# No arguments: show help
		typer.echo(app.get_help(), err=True)
		raise typer.Exit(0)
	app()

if __name__ == "__main__":
	main()
