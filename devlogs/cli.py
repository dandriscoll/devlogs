# CLI entrypoint for devlogs

import typer

app = typer.Typer()


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
