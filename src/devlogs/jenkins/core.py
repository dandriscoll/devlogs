# Core Jenkins integration functionality

import json
import os
import signal
import sys
import time
import urllib.request
import urllib.error
from base64 import b64encode
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..config import load_config
from ..opensearch.client import (
	get_opensearch_client,
	check_connection,
	check_index,
	OpenSearchError,
	ConnectionFailedError,
	AuthenticationError,
)


class JenkinsError(Exception):
	"""Base exception for Jenkins-related errors."""
	pass


class JenkinsAuthError(JenkinsError):
	"""Raised when Jenkins authentication fails."""
	pass


class JenkinsBuildNotFoundError(JenkinsError):
	"""Raised when Jenkins build cannot be found."""
	pass


class JenkinsEnvironmentError(JenkinsError):
	"""Raised when required Jenkins environment variables are missing."""
	pass


@dataclass
class JenkinsBuildInfo:
	"""Information about a Jenkins build."""
	build_url: str
	job_name: Optional[str] = None
	build_number: Optional[str] = None
	build_tag: Optional[str] = None
	branch_name: Optional[str] = None
	git_commit: Optional[str] = None

	@property
	def run_id(self) -> str:
		"""Get the run ID for this build (uses BUILD_TAG if available)."""
		return self.build_tag or f"jenkins-{self.job_name or 'unknown'}-{self.build_number or 'unknown'}"


def detect_jenkins_environment(build_url: Optional[str] = None) -> JenkinsBuildInfo:
	"""Detect Jenkins build information from environment variables.

	Args:
		build_url: Optional explicit build URL (overrides env var)

	Returns:
		JenkinsBuildInfo with detected values

	Raises:
		JenkinsEnvironmentError: If BUILD_URL is not present and not provided
	"""
	url = build_url or os.getenv("BUILD_URL")
	if not url:
		raise JenkinsEnvironmentError(
			"BUILD_URL environment variable is not set.\n"
			"This command must be run from within a Jenkins build, or use --url."
		)

	return JenkinsBuildInfo(
		build_url=url.rstrip("/") + "/",  # Ensure trailing slash
		job_name=os.getenv("JOB_NAME"),
		build_number=os.getenv("BUILD_NUMBER"),
		build_tag=os.getenv("BUILD_TAG"),
		branch_name=os.getenv("BRANCH_NAME"),
		git_commit=os.getenv("GIT_COMMIT"),
	)


def get_jenkins_auth_headers() -> dict:
	"""Get authentication headers for Jenkins API requests.

	Returns:
		Dict with Authorization header if credentials are available, empty dict otherwise.
	"""
	user = os.getenv("JENKINS_USER")
	token = os.getenv("JENKINS_TOKEN")

	if user and token:
		credentials = b64encode(f"{user}:{token}".encode()).decode('ascii')
		return {"Authorization": f"Basic {credentials}"}
	return {}


class JenkinsLogStreamer:
	"""Streams logs from Jenkins progressive console API."""

	def __init__(self, build_info: JenkinsBuildInfo, timeout: int = 30):
		self.build_info = build_info
		self.timeout = timeout
		self.offset = 0
		self.auth_headers = get_jenkins_auth_headers()
		self._more_data = True

	def _make_request(self, url: str) -> urllib.request.Request:
		"""Create a request with optional authentication."""
		headers = dict(self.auth_headers)
		return urllib.request.Request(url, headers=headers, method="GET")

	def fetch_next_chunk(self) -> tuple[str, bool]:
		"""Fetch the next chunk of logs from Jenkins.

		Returns:
			Tuple of (log_text, more_data_available)

		Raises:
			JenkinsAuthError: If authentication fails
			JenkinsError: For other Jenkins API errors
		"""
		url = f"{self.build_info.build_url}logText/progressiveText?start={self.offset}"
		req = self._make_request(url)

		try:
			with urllib.request.urlopen(req, timeout=self.timeout) as resp:
				text = resp.read().decode('utf-8', errors='replace')
				# Read headers for next offset
				text_size = resp.headers.get("X-Text-Size")
				more_data = resp.headers.get("X-More-Data", "").lower() == "true"

				if text_size:
					self.offset = int(text_size)

				self._more_data = more_data
				return text, more_data

		except urllib.error.HTTPError as e:
			if e.code in (401, 403):
				raise JenkinsAuthError(
					f"Jenkins authentication failed (HTTP {e.code}).\n"
					"Set JENKINS_USER and JENKINS_TOKEN environment variables."
				)
			raise JenkinsError(f"Jenkins API error: HTTP {e.code} - {e.reason}")
		except urllib.error.URLError as e:
			raise JenkinsError(f"Cannot connect to Jenkins: {e.reason}")

	def is_build_running(self) -> bool:
		"""Check if the Jenkins build is still running.

		Returns:
			True if build is running, False if completed
		"""
		url = f"{self.build_info.build_url}api/json?tree=building"
		req = self._make_request(url)

		try:
			with urllib.request.urlopen(req, timeout=self.timeout) as resp:
				data = json.loads(resp.read().decode('utf-8'))
				return data.get("building", False)
		except urllib.error.HTTPError as e:
			if e.code in (401, 403):
				raise JenkinsAuthError(
					f"Jenkins authentication failed (HTTP {e.code}).\n"
					"Set JENKINS_USER and JENKINS_TOKEN environment variables."
				)
			# If we can't check, assume it's running
			return True
		except (urllib.error.URLError, json.JSONDecodeError):
			# If we can't check, assume it's running
			return True

	@property
	def has_more_data(self) -> bool:
		"""Whether more data was indicated by the last response."""
		return self._more_data

	@property
	def current_offset(self) -> int:
		"""Current byte offset in the log."""
		return self.offset

	def set_offset(self, offset: int):
		"""Set the current offset (for resume functionality)."""
		self.offset = offset


class JenkinsLogIndexer:
	"""Indexes Jenkins logs to OpenSearch with progressive bulk indexing."""

	def __init__(self, build_info: JenkinsBuildInfo, batch_size: int = 100):
		self.build_info = build_info
		self.batch_size = batch_size
		self.config = load_config()
		self.client = get_opensearch_client()
		self.seq = 0  # Monotonically increasing sequence number
		self._buffer = []

	def _create_document(self, line: str, line_offset: int) -> dict:
		"""Create a document for a single log line."""
		now = datetime.now(timezone.utc).isoformat()
		self.seq += 1
		return {
			"doc_type": "jenkins_log",
			"timestamp": now,
			"run_id": self.build_info.run_id,
			"job": self.build_info.job_name,
			"build_number": self.build_info.build_number,
			"build_url": self.build_info.build_url,
			"branch": self.build_info.branch_name,
			"git_commit": self.build_info.git_commit,
			"seq": self.seq,
			"byte_offset": line_offset,
			"message": line,
			"source": "jenkins",
			"level": "info",  # Default level, could be enhanced with log parsing
		}

	def index_chunk(self, text: str, start_offset: int):
		"""Index a chunk of log text.

		Args:
			text: The log text to index
			start_offset: The byte offset of the start of this chunk
		"""
		if not text.strip():
			return

		lines = text.splitlines()
		current_offset = start_offset

		for line in lines:
			if line.strip():  # Skip empty lines
				doc = self._create_document(line, current_offset)
				self._buffer.append({"index": {"_index": self.config.index}})
				self._buffer.append(doc)

			current_offset += len(line) + 1  # +1 for newline

			# Flush if buffer is full
			if len(self._buffer) >= self.batch_size * 2:  # *2 because of action/doc pairs
				self._flush()

	def _flush(self):
		"""Flush buffered documents to OpenSearch."""
		if not self._buffer:
			return

		try:
			self.client.bulk(self._buffer)
			self._buffer = []
		except OpenSearchError as e:
			# Log error but don't fail - we want to continue streaming
			print(f"Warning: Failed to index logs: {e}", file=sys.stderr)
			self._buffer = []

	def flush(self):
		"""Force flush any remaining buffered documents."""
		self._flush()

	def get_last_indexed_offset(self) -> int:
		"""Get the last indexed byte offset for resume functionality.

		Returns:
			The highest byte_offset indexed, or 0 if none found
		"""
		query = {
			"query": {
				"bool": {
					"must": [
						{"term": {"run_id": self.build_info.run_id}},
						{"term": {"source": "jenkins"}},
					]
				}
			},
			"sort": [{"byte_offset": {"order": "desc"}}],
			"size": 1,
			"_source": ["byte_offset"],
		}

		try:
			result = self.client.search(self.config.index, query)
			hits = result.get("hits", {}).get("hits", [])
			if hits:
				return hits[0].get("_source", {}).get("byte_offset", 0)
		except OpenSearchError:
			pass

		return 0


# State file management for background mode
STATE_FILE_NAME = ".devlogs-jenkins-state.json"


def get_state_file_path() -> Path:
	"""Get the path to the state file in the current workspace."""
	# Try WORKSPACE env var first (Jenkins sets this)
	workspace = os.getenv("WORKSPACE")
	if workspace:
		return Path(workspace) / STATE_FILE_NAME
	# Fall back to current directory
	return Path.cwd() / STATE_FILE_NAME


@dataclass
class AttachState:
	"""State for a running attach process."""
	pid: int
	run_id: str
	build_url: str
	offset: int
	started_at: str

	def to_dict(self) -> dict:
		return {
			"pid": self.pid,
			"run_id": self.run_id,
			"build_url": self.build_url,
			"offset": self.offset,
			"started_at": self.started_at,
		}

	@classmethod
	def from_dict(cls, data: dict) -> "AttachState":
		return cls(
			pid=data["pid"],
			run_id=data["run_id"],
			build_url=data["build_url"],
			offset=data.get("offset", 0),
			started_at=data.get("started_at", ""),
		)


def write_state(state: AttachState):
	"""Write the attach state to the state file."""
	path = get_state_file_path()
	path.write_text(json.dumps(state.to_dict(), indent=2))


def read_state() -> Optional[AttachState]:
	"""Read the attach state from the state file."""
	path = get_state_file_path()
	if not path.exists():
		return None
	try:
		data = json.loads(path.read_text())
		return AttachState.from_dict(data)
	except (json.JSONDecodeError, KeyError):
		return None


def clear_state():
	"""Remove the state file."""
	path = get_state_file_path()
	if path.exists():
		path.unlink()


def update_state_offset(offset: int):
	"""Update just the offset in the state file."""
	state = read_state()
	if state:
		state.offset = offset
		write_state(state)


def is_process_running(pid: int) -> bool:
	"""Check if a process with the given PID is running."""
	try:
		os.kill(pid, 0)
		return True
	except OSError:
		return False


def stop_attach_process() -> bool:
	"""Stop a running attach process.

	Returns:
		True if process was stopped, False if no process was running
	"""
	state = read_state()
	if not state:
		return False

	if not is_process_running(state.pid):
		clear_state()
		return False

	try:
		os.kill(state.pid, signal.SIGTERM)
		# Wait a bit for graceful shutdown
		for _ in range(10):
			time.sleep(0.1)
			if not is_process_running(state.pid):
				break
		clear_state()
		return True
	except OSError:
		clear_state()
		return False


def run_attach(
	build_info: JenkinsBuildInfo,
	background: bool = False,
	resume: bool = True,
	verbose: bool = False,
):
	"""Run the attach process to stream Jenkins logs to OpenSearch.

	Args:
		build_info: Jenkins build information
		background: If True, fork into background
		resume: If True, resume from last indexed offset
		verbose: If True, print progress messages
	"""
	if background:
		_run_background(build_info, resume, verbose)
	else:
		_run_foreground(build_info, resume, verbose)


def _run_background(build_info: JenkinsBuildInfo, resume: bool, verbose: bool):
	"""Fork into background and run the attach process."""
	# Double fork to daemonize
	pid = os.fork()
	if pid > 0:
		# Parent process - exit immediately
		if verbose:
			print(f"Started background process with PID {pid}")
		return

	# Child process
	os.setsid()  # Create new session

	# Second fork
	pid = os.fork()
	if pid > 0:
		os._exit(0)

	# Grandchild process - this is our daemon
	# Redirect stdout/stderr to /dev/null
	sys.stdout.flush()
	sys.stderr.flush()
	with open(os.devnull, 'w') as devnull:
		os.dup2(devnull.fileno(), sys.stdout.fileno())
		os.dup2(devnull.fileno(), sys.stderr.fileno())

	# Write state file
	state = AttachState(
		pid=os.getpid(),
		run_id=build_info.run_id,
		build_url=build_info.build_url,
		offset=0,
		started_at=datetime.now(timezone.utc).isoformat(),
	)
	write_state(state)

	# Set up signal handler for graceful shutdown
	def handle_signal(signum, frame):
		clear_state()
		sys.exit(0)

	signal.signal(signal.SIGTERM, handle_signal)
	signal.signal(signal.SIGINT, handle_signal)

	try:
		_stream_logs(build_info, resume, verbose=False)
	finally:
		clear_state()


def _run_foreground(build_info: JenkinsBuildInfo, resume: bool, verbose: bool):
	"""Run the attach process in foreground."""
	# Write state file for stop command
	state = AttachState(
		pid=os.getpid(),
		run_id=build_info.run_id,
		build_url=build_info.build_url,
		offset=0,
		started_at=datetime.now(timezone.utc).isoformat(),
	)
	write_state(state)

	# Set up signal handler for graceful shutdown
	def handle_signal(signum, frame):
		clear_state()
		sys.exit(0)

	signal.signal(signal.SIGTERM, handle_signal)

	try:
		_stream_logs(build_info, resume, verbose)
	finally:
		clear_state()


def _stream_logs(build_info: JenkinsBuildInfo, resume: bool, verbose: bool):
	"""Stream logs from Jenkins to OpenSearch.

	Args:
		build_info: Jenkins build information
		resume: If True, resume from last indexed offset
		verbose: If True, print progress messages
	"""
	streamer = JenkinsLogStreamer(build_info)
	indexer = JenkinsLogIndexer(build_info)

	# Resume from last offset if requested
	if resume:
		last_offset = indexer.get_last_indexed_offset()
		if last_offset > 0:
			streamer.set_offset(last_offset)
			if verbose:
				print(f"Resuming from offset {last_offset}")

	consecutive_errors = 0
	max_errors = 5

	while True:
		try:
			chunk, more_data = streamer.fetch_next_chunk()
			consecutive_errors = 0

			if chunk:
				indexer.index_chunk(chunk, streamer.current_offset - len(chunk))
				update_state_offset(streamer.current_offset)
				if verbose:
					lines = len(chunk.splitlines())
					print(f"Indexed {lines} lines (offset: {streamer.current_offset})")

			# Check if build is complete
			if not more_data:
				if not streamer.is_build_running():
					if verbose:
						print("Build completed, flushing and exiting")
					indexer.flush()
					break
				# Build still running but no new data - longer sleep
				time.sleep(1.0)
			else:
				# More data available - short sleep
				time.sleep(0.25)

		except JenkinsAuthError as e:
			print(f"Error: {e}", file=sys.stderr)
			indexer.flush()
			sys.exit(1)

		except JenkinsError as e:
			consecutive_errors += 1
			if consecutive_errors >= max_errors:
				print(f"Error: Too many failures ({consecutive_errors}): {e}", file=sys.stderr)
				indexer.flush()
				sys.exit(1)
			if verbose:
				print(f"Warning: {e} (attempt {consecutive_errors}/{max_errors})")
			time.sleep(2.0)

		except OpenSearchError as e:
			consecutive_errors += 1
			if consecutive_errors >= max_errors:
				print(f"Error: Too many OpenSearch failures ({consecutive_errors}): {e}", file=sys.stderr)
				sys.exit(1)
			if verbose:
				print(f"Warning: OpenSearch error: {e} (attempt {consecutive_errors}/{max_errors})")
			time.sleep(2.0)

	if verbose:
		print(f"Finished indexing {indexer.seq} log entries")


def run_snapshot(build_info: JenkinsBuildInfo, verbose: bool = False):
	"""Take a one-time snapshot of the current Jenkins logs.

	Unlike attach, this doesn't stream - it just captures the current state.

	Args:
		build_info: Jenkins build information
		verbose: If True, print progress messages
	"""
	streamer = JenkinsLogStreamer(build_info)
	indexer = JenkinsLogIndexer(build_info)

	if verbose:
		print(f"Taking snapshot of {build_info.build_url}")

	# Fetch all available logs in chunks
	while True:
		chunk, more_data = streamer.fetch_next_chunk()

		if chunk:
			indexer.index_chunk(chunk, streamer.current_offset - len(chunk))
			if verbose:
				lines = len(chunk.splitlines())
				print(f"Indexed {lines} lines (offset: {streamer.current_offset})")

		if not more_data:
			break

		# Small sleep to avoid hammering Jenkins
		time.sleep(0.1)

	indexer.flush()

	if verbose:
		print(f"Snapshot complete: {indexer.seq} log entries indexed")
