# CLI entrypoint for the devlogs collector service
#
# Run standalone:
#   devlogs-collector
#   devlogs-collector --port 8080 --host 0.0.0.0
#
# Or as a module:
#   python -m devlogs.collector

import signal
import sys

# Handle Ctrl+C gracefully before any other imports
signal.signal(signal.SIGINT, lambda *_: sys.exit(130))

import typer
from typing import Optional

app = typer.Typer(
    name="devlogs-collector",
    help="Devlogs HTTP log collector service",
)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8080, "--port", "-p", help="Port to listen on"),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of worker processes"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),
    log_level: str = typer.Option("info", "--log-level", help="Log level (debug, info, warning, error)"),
):
    """Start the collector HTTP server.

    The collector operates in one of two modes based on environment configuration:

    FORWARD MODE: Set DEVLOGS_FORWARD_URL to proxy requests to an upstream collector.

    INGEST MODE: Set DEVLOGS_OPENSEARCH_* variables to write directly to OpenSearch.

    Example:
        # Start in ingest mode
        DEVLOGS_OPENSEARCH_HOST=localhost devlogs-collector serve

        # Start in forward mode
        DEVLOGS_FORWARD_URL=http://upstream:8080 devlogs-collector serve

        # Production with multiple workers
        devlogs-collector serve --workers 4 --host 0.0.0.0 --port 8080
    """
    try:
        import uvicorn
    except ImportError:
        typer.echo(typer.style("Error: uvicorn is required. Install with: pip install uvicorn", fg=typer.colors.RED), err=True)
        raise typer.Exit(1)

    from ..config import load_config

    # Check configuration and show mode
    cfg = load_config()
    mode = cfg.get_collector_mode()

    if mode == "error":
        typer.echo(typer.style(
            "Warning: Collector not fully configured. "
            "Set DEVLOGS_FORWARD_URL or DEVLOGS_OPENSEARCH_* environment variables.",
            fg=typer.colors.YELLOW
        ))
    else:
        mode_str = "FORWARD" if mode == "forward" else "INGEST"
        typer.echo(typer.style(f"Starting collector in {mode_str} mode", fg=typer.colors.GREEN))
        if mode == "forward":
            typer.echo(f"  Forwarding to: {cfg.forward_url}")
        else:
            typer.echo(f"  OpenSearch: {cfg.opensearch_host}:{cfg.opensearch_port}")
            typer.echo(f"  Index: {cfg.index}")

    typer.echo(f"  Listening on: {host}:{port}")
    typer.echo()

    # Run the server
    uvicorn.run(
        "devlogs.collector.server:app",
        host=host,
        port=port,
        workers=workers if not reload else 1,  # Can't use workers with reload
        reload=reload,
        log_level=log_level,
    )


@app.command()
def check():
    """Check collector configuration and connectivity.

    Validates that the collector is properly configured and can reach
    its backend (either forward URL or OpenSearch).
    """
    from ..config import load_config

    cfg = load_config()
    mode = cfg.get_collector_mode()

    typer.echo(typer.style("Collector Configuration Check", bold=True))
    typer.echo()

    # Show mode
    if mode == "error":
        typer.echo(typer.style("Mode: NOT CONFIGURED", fg=typer.colors.RED))
        typer.echo("  Set DEVLOGS_FORWARD_URL or DEVLOGS_OPENSEARCH_* variables")
        raise typer.Exit(1)
    elif mode == "forward":
        typer.echo(typer.style("Mode: FORWARD", fg=typer.colors.CYAN))
        typer.echo(f"  Forward URL: {cfg.forward_url}")
    else:
        typer.echo(typer.style("Mode: INGEST", fg=typer.colors.CYAN))
        typer.echo(f"  OpenSearch Host: {cfg.opensearch_host}")
        typer.echo(f"  OpenSearch Port: {cfg.opensearch_port}")
        typer.echo(f"  Index: {cfg.index}")

    # Show limits (if configured)
    if cfg.collector_rate_limit > 0:
        typer.echo(f"  Rate Limit: {cfg.collector_rate_limit} req/s")
    if cfg.collector_max_payload_size > 0:
        typer.echo(f"  Max Payload: {cfg.collector_max_payload_size} bytes")

    typer.echo()

    # Test connectivity
    if mode == "ingest":
        typer.echo("Testing OpenSearch connectivity...")
        try:
            from ..opensearch.client import get_opensearch_client, check_connection
            client = get_opensearch_client()
            check_connection(client)
            typer.echo(typer.style("  OpenSearch: OK", fg=typer.colors.GREEN))

            # Check if index exists
            if client.indices.exists(index=cfg.index):
                typer.echo(typer.style(f"  Index '{cfg.index}': EXISTS", fg=typer.colors.GREEN))
            else:
                typer.echo(typer.style(f"  Index '{cfg.index}': NOT FOUND", fg=typer.colors.YELLOW))
                typer.echo("    Run 'devlogs init' to create the index")
        except Exception as e:
            typer.echo(typer.style(f"  OpenSearch: FAILED - {e}", fg=typer.colors.RED))
            raise typer.Exit(1)
    else:
        typer.echo("Testing forward URL connectivity...")
        try:
            import urllib.request
            import urllib.error
            # Just test that we can resolve the host (don't actually POST)
            req = urllib.request.Request(cfg.forward_url, method="HEAD")
            try:
                with urllib.request.urlopen(req, timeout=5):
                    pass
                typer.echo(typer.style("  Forward URL: OK", fg=typer.colors.GREEN))
            except urllib.error.HTTPError as e:
                # Any HTTP response means the server is reachable
                if e.code in (404, 405, 400):
                    typer.echo(typer.style("  Forward URL: REACHABLE", fg=typer.colors.GREEN))
                else:
                    typer.echo(typer.style(f"  Forward URL: HTTP {e.code}", fg=typer.colors.YELLOW))
        except urllib.error.URLError as e:
            typer.echo(typer.style(f"  Forward URL: UNREACHABLE - {e.reason}", fg=typer.colors.RED))
            raise typer.Exit(1)
        except Exception as e:
            typer.echo(typer.style(f"  Forward URL: FAILED - {e}", fg=typer.colors.RED))
            raise typer.Exit(1)

    typer.echo()
    typer.echo(typer.style("All checks passed!", fg=typer.colors.GREEN))


def main():
    """Main entry point for the collector CLI."""
    app()


if __name__ == "__main__":
    main()
