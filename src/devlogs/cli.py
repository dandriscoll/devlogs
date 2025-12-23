import signal
import sys

# Handle Ctrl+C gracefully before any other imports
signal.signal(signal.SIGINT, lambda *_: sys.exit(130))

import logging
import random
import time
import typer

from .config import load_config
from .context import operation, set_area
from .handler import OpenSearchHandler
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


@app.command()
def demo(
	duration: int = typer.Option(10, "--duration", "-t", help="Duration in seconds"),
	count: int = typer.Option(50, "--count", "-n", help="Number of log entries to generate"),
):
	"""Generate demo logs to illustrate devlogs capabilities."""
	cfg = load_config()

	# Show loaded configuration
	typer.echo("=== DevLogs Demo ===\n")
	typer.echo("Configuration loaded from .env:")
	typer.echo(f"  OPENSEARCH_HOST: {cfg.opensearch_host}")
	typer.echo(f"  OPENSEARCH_PORT: {cfg.opensearch_port}")
	typer.echo(f"  OPENSEARCH_USER: {cfg.opensearch_user}")
	typer.echo(f"  OPENSEARCH_PASS: {'*' * len(cfg.opensearch_pass)}")
	typer.echo(f"  DEVLOGS_INDEX_LOGS: {cfg.index_logs}")
	typer.echo(f"  DEVLOGS_AREA_DEFAULT: {cfg.area_default}")
	typer.echo(f"  DEVLOGS_RETENTION_DEBUG_HOURS: {cfg.retention_debug_hours}")
	typer.echo("")

	# Set up logging with OpenSearch handler
	client = get_opensearch_client()
	handler = OpenSearchHandler(
		level=logging.DEBUG,
		opensearch_client=client,
		index_name=cfg.index_logs,
	)
	handler.setFormatter(logging.Formatter("%(message)s"))

	logger = logging.getLogger("devlogs.demo")
	logger.setLevel(logging.DEBUG)
	logger.addHandler(handler)

	# Also log to console
	console = logging.StreamHandler()
	console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s [%(name)s] %(message)s"))
	logger.addHandler(console)

	# Calculate delay to spread logs over duration
	delay = duration / count
	typer.echo(f"Streaming {count} log entries over {duration} seconds...\n")

	# Demo scenarios with time tracking
	areas = ["api", "database", "auth", "payments", "notifications", "scheduler"]
	users = ["alice", "bob", "charlie", "diana", "eve"]
	endpoints = ["/api/users", "/api/orders", "/api/products", "/api/checkout", "/api/search"]
	tables = ["users", "orders", "products", "sessions", "audit_log"]
	jobs = ["cleanup_sessions", "send_reminders", "generate_reports", "sync_inventory"]
	channels = ["email", "sms", "push", "webhook"]

	generated = 0
	start_time = time.time()
	last_countdown = duration + 1

	def check_countdown():
		"""Print countdown messages."""
		nonlocal last_countdown
		elapsed = time.time() - start_time
		remaining = max(0, duration - int(elapsed))
		if remaining < last_countdown:
			last_countdown = remaining
			if remaining > 0:
				typer.echo(typer.style(f"\n--- {remaining} seconds remaining ---\n", fg=typer.colors.CYAN))

	def emit_log():
		"""Emit a random log entry based on current scenario."""
		nonlocal generated
		scenario = random.choices(
			["api", "database", "auth", "payments", "scheduler", "notifications", "burst"],
			weights=[20, 15, 15, 10, 10, 10, 20],
		)[0]

		if scenario == "api":
			with operation(area="api"):
				endpoint = random.choice(endpoints)
				user = random.choice(users)
				latency = random.randint(10, 500)
				log_type = random.choice(["request", "response", "error"])
				if log_type == "request":
					logger.debug(f"Request received: GET {endpoint} from user={user}")
				elif log_type == "response":
					if latency > 400:
						logger.warning(f"Slow response: {latency}ms for {endpoint}")
					else:
						logger.info(f"Response sent: {endpoint} in {latency}ms")
				else:
					logger.error(f"Request failed: {endpoint} - connection timeout")

		elif scenario == "database":
			with operation(area="database"):
				table = random.choice(tables)
				rows = random.randint(1, 1000)
				query_time = random.randint(1, 200)
				if query_time > 150:
					logger.warning(f"Slow query: {query_time}ms on {table}")
				elif random.random() < 0.1:
					logger.error(f"Deadlock detected on table={table}, retrying...")
				else:
					logger.info(f"Query returned {rows} rows from {table}")

		elif scenario == "auth":
			with operation(area="auth"):
				user = random.choice(users)
				action = random.choice(["login_success", "login_fail", "logout", "token"])
				if action == "login_success":
					logger.info(f"Successful login: user={user}")
				elif action == "login_fail":
					logger.warning(f"Failed login attempt for user={user}")
				elif action == "logout":
					logger.info(f"User logged out: user={user}")
				else:
					logger.debug(f"Token refreshed for user={user}")

		elif scenario == "payments":
			with operation(area="payments"):
				amount = random.randint(10, 500)
				order_id = f"ORD-{random.randint(10000, 99999)}"
				if random.random() < 0.15:
					logger.error(f"Payment declined: {order_id} reason=insufficient_funds")
				else:
					logger.info(f"Payment successful: {order_id} amount=${amount}")

		elif scenario == "scheduler":
			with operation(area="scheduler"):
				job = random.choice(jobs)
				job_duration = random.randint(100, 5000)
				if random.random() < 0.5:
					logger.info(f"Job started: {job}")
				elif job_duration > 4000:
					logger.warning(f"Job {job} taking longer than expected: {job_duration}ms")
				else:
					logger.info(f"Job completed: {job} in {job_duration}ms")

		elif scenario == "notifications":
			with operation(area="notifications"):
				channel = random.choice(channels)
				user = random.choice(users)
				if channel == "sms" and random.random() < 0.15:
					logger.error(f"SMS delivery failed for user={user}: carrier_error")
				elif channel == "webhook" and random.random() < 0.2:
					logger.warning(f"Webhook timeout for user={user}, will retry")
				else:
					logger.info(f"Notification sent via {channel} to user={user}")

		else:  # burst
			with operation(area="api"):
				level = random.choices(
					[logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL],
					weights=[30, 40, 15, 10, 5],
				)[0]
				messages = {
					logging.DEBUG: "Cache miss, fetching from source",
					logging.INFO: "Request processed successfully",
					logging.WARNING: "Rate limit approaching threshold",
					logging.ERROR: "Service temporarily unavailable",
					logging.CRITICAL: "Circuit breaker triggered, failing fast",
				}
				logger.log(level, messages[level])

		generated += 1

	# Main loop: emit logs and show countdown
	while generated < count:
		check_countdown()
		emit_log()
		time.sleep(delay)

	elapsed = time.time() - start_time
	typer.echo(typer.style(f"\n--- Demo complete! ---", fg=typer.colors.GREEN))
	typer.echo(f"Generated {generated} log entries in {elapsed:.1f} seconds.")
	typer.echo(f"View logs with: devlogs tail --follow")


def main():
	if len(sys.argv) == 1:
		# No arguments: show help
		typer.echo(app.get_help(), err=True)
		raise typer.Exit(0)
	app()

if __name__ == "__main__":
	main()
