# Demo command for devlogs CLI

import logging
import random
import time
import typer

from .config import load_config
from .context import operation, set_rollup_default
from .handler import OpenSearchHandler


def run_demo(
	duration: int,
	count: int,
	require_opensearch,
	defer_rollup: bool,
):
	"""Generate demo logs to illustrate devlogs capabilities."""
	cfg = load_config()
	set_rollup_default(not defer_rollup)

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

	# Check OpenSearch connection and index
	client, cfg = require_opensearch()
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
			["api", "auth", "payments", "scheduler", "notifications"],
			weights=[35, 20, 15, 15, 15],
		)[0]

		if scenario == "api":
			# API request with auth check and database query
			with operation(area="api"):
				endpoint = random.choice(endpoints)
				user = random.choice(users)
				logger.info(f"Request received: GET {endpoint} from user={user}")

				# Auth check
				with operation(area="auth"):
					if random.random() < 0.1:
						logger.warning(f"Token near expiry for user={user}")
					else:
						logger.debug(f"Token validated for user={user}")

				# Database query
				with operation(area="database"):
					table = random.choice(tables)
					rows = random.randint(1, 1000)
					query_time = random.randint(1, 200)
					if query_time > 150:
						logger.warning(f"Slow query: {query_time}ms on {table}")
					elif random.random() < 0.05:
						logger.error(f"Deadlock detected on table={table}, retrying...")
					else:
						logger.info(f"Query returned {rows} rows from {table}")

				# Response
				latency = random.randint(50, 500)
				if random.random() < 0.1:
					logger.error(f"Request failed: {endpoint} - connection timeout")
				elif latency > 400:
					logger.warning(f"Slow response: {latency}ms for {endpoint}")
				else:
					logger.info(f"Response sent: {endpoint} in {latency}ms")

		elif scenario == "auth":
			# Auth operation with database lookup and optional notification
			with operation(area="auth"):
				user = random.choice(users)
				action = random.choice(["login", "logout", "token"])

				if action == "login":
					logger.info(f"Login attempt for user={user}")

					# Database lookup
					with operation(area="database"):
						logger.debug(f"Looking up credentials for user={user}")

					if random.random() < 0.2:
						logger.warning(f"Failed login attempt for user={user}")
						# Send security notification
						with operation(area="notifications"):
							logger.info(f"Security alert sent to user={user}")
					else:
						logger.info(f"Successful login: user={user}")

				elif action == "logout":
					logger.info(f"User logged out: user={user}")
					with operation(area="database"):
						logger.debug(f"Session cleared for user={user}")

				else:
					logger.debug(f"Token refresh requested for user={user}")
					with operation(area="database"):
						logger.debug(f"Token validated for user={user}")

		elif scenario == "payments":
			# Payment with auth, database, and notification
			with operation(area="payments"):
				amount = random.randint(10, 500)
				order_id = f"ORD-{random.randint(10000, 99999)}"
				logger.info(f"Processing payment for {order_id}")

				# Auth verification
				with operation(area="auth"):
					logger.debug(f"Verifying payment authorization for {order_id}")

				# Database update
				with operation(area="database"):
					if random.random() < 0.15:
						logger.error(f"Payment declined: {order_id} reason=insufficient_funds")
					else:
						logger.info(f"Payment recorded: {order_id} amount=${amount}")

						# Send receipt notification
						with operation(area="notifications"):
							channel = random.choice(["email", "sms"])
							logger.info(f"Receipt sent via {channel} for {order_id}")

		elif scenario == "scheduler":
			# Scheduled job with database operations
			with operation(area="scheduler"):
				job = random.choice(jobs)
				logger.info(f"Job started: {job}")

				# Database operations during job
				with operation(area="database"):
					table = random.choice(tables)
					if job == "cleanup_sessions":
						rows = random.randint(10, 500)
						logger.info(f"Cleaned up {rows} expired sessions")
					elif job == "generate_reports":
						query_time = random.randint(100, 2000)
						if query_time > 1500:
							logger.warning(f"Slow report query: {query_time}ms on {table}")
						else:
							logger.info(f"Report data fetched from {table}")
					else:
						logger.debug(f"Processing {table} records")

				job_duration = random.randint(100, 5000)
				if job_duration > 4000:
					logger.warning(f"Job {job} took longer than expected: {job_duration}ms")
				else:
					logger.info(f"Job completed: {job} in {job_duration}ms")

		else:  # notifications
			# Notification with optional database logging
			with operation(area="notifications"):
				channel = random.choice(channels)
				user = random.choice(users)
				logger.info(f"Sending {channel} notification to user={user}")

				# Log to database
				with operation(area="database"):
					logger.debug(f"Recording notification in audit_log")

				if channel == "sms" and random.random() < 0.15:
					logger.error(f"SMS delivery failed for user={user}: carrier_error")
				elif channel == "webhook" and random.random() < 0.2:
					logger.warning(f"Webhook timeout for user={user}, will retry")
				else:
					logger.info(f"Notification delivered via {channel} to user={user}")

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
