import typer

from .config import load_config
from .opensearch.client import get_opensearch_client
from .opensearch.mappings import LOG_INDEX_TEMPLATE

app = typer.Typer()


@app.command()
def init():
	"""Initialize OpenSearch indices and templates (idempotent)."""
	cfg = load_config()
	client = get_opensearch_client()
	# Create or update index templates
	client.indices.put_index_template(name="devlogs-logs-template", body=LOG_INDEX_TEMPLATE)
	# Create initial indices if not exist
	if not client.indices.exists(index=cfg.index_logs):
		client.indices.create(index=cfg.index_logs)
	typer.echo("OpenSearch indices and templates initialized.")


@app.command()
def tail(area: str = "web", follow: bool = False):
	"""Tail logs for a given area (stub)."""
	typer.echo(f"[stub] Tailing logs for area: {area}, follow={follow}")


@app.command()
def search(q: str = "", area: str = "web"):
	"""Search logs for a query (stub)."""
	typer.echo(f"[stub] Searching logs for area: {area}, query='{q}'")

def main():
	import sys
	if len(sys.argv) == 1:
		# No arguments: show help
		typer.echo(app.get_help(), err=True)
		raise typer.Exit(0)
	app()

if __name__ == "__main__":
	main()
