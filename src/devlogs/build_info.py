# Build info helper for devlogs
#
# Provides a stable build identifier that applications can use as a field
# in log entries without requiring git at runtime.

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal, Optional, Union

# Default file name for build info
DEFAULT_BUILD_INFO_FILENAME = ".build.json"

# Default environment variable prefix
DEFAULT_ENV_PREFIX = "DEVLOGS_"

# Maximum number of parent directories to search for build info file
DEFAULT_MAX_SEARCH_DEPTH = 10


@dataclass
class BuildInfo:
    """Build information resolved from file, environment, or generated."""

    build_id: str
    """Unique build identifier (always non-empty)."""

    branch: Optional[str]
    """Branch name if available."""

    timestamp_utc: str
    """UTC timestamp in format YYYYMMDDTHHMMSSZ."""

    source: Literal["file", "env", "generated"]
    """Source of the build info: 'file', 'env', or 'generated'."""

    path: Optional[str]
    """File path used for build info, if any."""


def _format_timestamp(dt: datetime) -> str:
    """Format datetime as compact ISO-like UTC timestamp: YYYYMMDDTHHMMSSZ."""
    utc_dt = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return utc_dt.strftime("%Y%m%dT%H%M%SZ")


def _find_build_info_file(
    path: Optional[Union[str, Path]],
    filename: str,
    max_depth: int,
) -> Optional[Path]:
    """
    Search for build info file.

    If path is provided, use it directly.
    Otherwise, search upward from cwd for filename.
    """
    # Check env override first
    env_path = os.environ.get(f"{DEFAULT_ENV_PREFIX}BUILD_INFO_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p
        return None

    if path is not None:
        p = Path(path)
        if p.exists():
            return p
        return None

    # Search upward from cwd
    current = Path.cwd()
    for _ in range(max_depth):
        candidate = current / filename
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            # Reached filesystem root
            break
        current = parent

    return None


def _read_build_info_file(filepath: Path) -> Optional[dict]:
    """
    Read and parse build info JSON file.

    Returns parsed dict if valid, None if file is missing, invalid JSON,
    or missing required keys.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        # We need at least build_id or enough info to construct one
        # Just return the dict - caller decides what to use
        return data
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _get_git_branch() -> Optional[str]:
    """
    Get current git branch using git command.

    Returns None if git is not available or command fails.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            if branch and branch != "HEAD":
                return branch
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _get_git_short_commit() -> Optional[str]:
    """
    Get current git short commit hash.

    Returns None if git is not available or command fails.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _write_build_info_file(filepath: Path, build_info: BuildInfo) -> bool:
    """
    Write build info to JSON file.

    Returns True on success, False on failure.
    Never raises exceptions.
    """
    try:
        data = {
            "build_id": build_info.build_id,
            "branch": build_info.branch,
            "timestamp_utc": build_info.timestamp_utc,
        }
        # Ensure parent directory exists
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        return True
    except OSError:
        return False


def resolve_build_info(
    *,
    path: Optional[Union[str, Path]] = None,
    filename: str = DEFAULT_BUILD_INFO_FILENAME,
    env_prefix: str = DEFAULT_ENV_PREFIX,
    allow_git: bool = False,
    now_fn: Optional[Callable[[], datetime]] = None,
    write_if_missing: bool = False,
    max_search_depth: int = DEFAULT_MAX_SEARCH_DEPTH,
) -> BuildInfo:
    """
    Resolve build information from file, environment, or generate it.

    Priority order:
    1. Environment variable BUILD_ID (if set) takes highest precedence
    2. Build info file (if found and valid)
    3. Environment variables for branch/timestamp
    4. Git (if allow_git=True)
    5. Generated values

    Args:
        path: Explicit path to build info file. If None, searches upward from cwd.
        filename: Filename to search for (default: ".build.json").
        env_prefix: Environment variable prefix (default: "DEVLOGS_").
        allow_git: If True, may attempt git commands as fallback.
        now_fn: Function returning current datetime (for testing).
        write_if_missing: If True and no file exists, write resolved info to disk.
        max_search_depth: Maximum parent directories to search (default: 10).

    Returns:
        BuildInfo with resolved values.

    Never raises exceptions - always returns valid BuildInfo with at least
    a generated build_id.
    """
    if now_fn is None:
        now_fn = lambda: datetime.now(timezone.utc)

    # Environment variable names
    env_build_id = f"{env_prefix}BUILD_ID"
    env_branch = f"{env_prefix}BRANCH"
    env_timestamp = f"{env_prefix}BUILD_TIMESTAMP_UTC"

    # Check for direct BUILD_ID env override (highest precedence)
    direct_build_id = os.environ.get(env_build_id)
    if direct_build_id:
        # Still try to get branch and timestamp from env or generate them
        branch = os.environ.get(env_branch)
        timestamp = os.environ.get(env_timestamp)
        if not timestamp:
            timestamp = _format_timestamp(now_fn())
        return BuildInfo(
            build_id=direct_build_id,
            branch=branch,
            timestamp_utc=timestamp,
            source="env",
            path=None,
        )

    # Try to find and read build info file
    filepath = _find_build_info_file(path, filename, max_search_depth)
    file_data: Optional[dict] = None
    if filepath:
        file_data = _read_build_info_file(filepath)

    if file_data:
        # File found and valid - use its data
        # Allow env overrides for individual fields
        build_id = file_data.get("build_id")
        branch = os.environ.get(env_branch) or file_data.get("branch")
        timestamp = os.environ.get(env_timestamp) or file_data.get("timestamp_utc")

        if not timestamp:
            timestamp = _format_timestamp(now_fn())

        if build_id:
            return BuildInfo(
                build_id=build_id,
                branch=branch,
                timestamp_utc=timestamp,
                source="file",
                path=str(filepath),
            )
        # File exists but no build_id - fall through to generate

    # Check if env provides branch and/or timestamp
    env_branch_value = os.environ.get(env_branch)
    env_timestamp_value = os.environ.get(env_timestamp)

    # Determine branch
    branch: Optional[str] = None
    if env_branch_value:
        branch = env_branch_value
    elif allow_git:
        branch = _get_git_branch()

    # Determine timestamp
    timestamp: str
    if env_timestamp_value:
        timestamp = env_timestamp_value
    else:
        timestamp = _format_timestamp(now_fn())

    # Generate build_id
    branch_for_id = branch if branch else "unknown"
    build_id = f"{branch_for_id}-{timestamp}"

    # Determine source
    source: Literal["file", "env", "generated"]
    if env_branch_value or env_timestamp_value:
        source = "env"
    else:
        source = "generated"

    result = BuildInfo(
        build_id=build_id,
        branch=branch,
        timestamp_utc=timestamp,
        source=source,
        path=str(filepath) if filepath else None,
    )

    # Optionally write to file
    if write_if_missing and not file_data:
        write_path = filepath if filepath else Path.cwd() / filename
        _write_build_info_file(write_path, result)
        # Update path in result if we wrote it
        result = BuildInfo(
            build_id=result.build_id,
            branch=result.branch,
            timestamp_utc=result.timestamp_utc,
            source=result.source,
            path=str(write_path),
        )

    return result


def resolve_build_id(
    *,
    path: Optional[Union[str, Path]] = None,
    filename: str = DEFAULT_BUILD_INFO_FILENAME,
    env_prefix: str = DEFAULT_ENV_PREFIX,
    allow_git: bool = False,
    now_fn: Optional[Callable[[], datetime]] = None,
    write_if_missing: bool = False,
    max_search_depth: int = DEFAULT_MAX_SEARCH_DEPTH,
) -> str:
    """
    Convenience wrapper that returns only the build_id string.

    See resolve_build_info() for parameter documentation.

    Returns:
        Non-empty build identifier string.
    """
    return resolve_build_info(
        path=path,
        filename=filename,
        env_prefix=env_prefix,
        allow_git=allow_git,
        now_fn=now_fn,
        write_if_missing=write_if_missing,
        max_search_depth=max_search_depth,
    ).build_id


def generate_build_info_file(
    output_path: Optional[Union[str, Path]] = None,
    *,
    branch: Optional[str] = None,
    allow_git: bool = True,
    now_fn: Optional[Callable[[], datetime]] = None,
) -> Optional[Path]:
    """
    Generate a .build.json file for use at runtime.

    This is a utility for CI/CD pipelines to generate the build info file
    during the build process.

    Args:
        output_path: Where to write the file. Defaults to cwd/.build.json.
        branch: Explicit branch name. If None and allow_git=True, uses git.
        allow_git: If True, attempts to get branch from git.
        now_fn: Function returning current datetime (for testing).

    Returns:
        Path to written file, or None if write failed.
    """
    if now_fn is None:
        now_fn = lambda: datetime.now(timezone.utc)

    if output_path is None:
        output_path = Path.cwd() / DEFAULT_BUILD_INFO_FILENAME
    else:
        output_path = Path(output_path)

    # Determine branch
    if branch is None and allow_git:
        branch = _get_git_branch()

    timestamp = _format_timestamp(now_fn())
    branch_for_id = branch if branch else "unknown"
    build_id = f"{branch_for_id}-{timestamp}"

    build_info = BuildInfo(
        build_id=build_id,
        branch=branch,
        timestamp_utc=timestamp,
        source="generated",
        path=str(output_path),
    )

    if _write_build_info_file(output_path, build_info):
        return output_path
    return None
