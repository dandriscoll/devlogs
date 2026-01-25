# Tests for devlogs.build_info module

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

from devlogs.build_info import (
    BuildInfo,
    DEFAULT_BUILD_INFO_FILENAME,
    DEFAULT_ENV_PREFIX,
    generate_build_info_file,
    resolve_build_id,
    resolve_build_info,
    _format_timestamp,
    _find_build_info_file,
    _get_git_branch,
    _read_build_info_file,
)


# Fixed datetime for deterministic tests
FIXED_DATETIME = datetime(2026, 1, 24, 15, 30, 45, tzinfo=timezone.utc)
FIXED_TIMESTAMP = "20260124T153045Z"


def fixed_now() -> datetime:
    """Return a fixed datetime for deterministic tests."""
    return FIXED_DATETIME


class TestFormatTimestamp:
    """Tests for _format_timestamp helper."""

    def test_format_utc_datetime(self):
        dt = datetime(2026, 3, 15, 10, 20, 30, tzinfo=timezone.utc)
        assert _format_timestamp(dt) == "20260315T102030Z"

    def test_format_naive_datetime(self):
        # Naive datetime is treated as UTC
        dt = datetime(2026, 3, 15, 10, 20, 30)
        assert _format_timestamp(dt) == "20260315T102030Z"

    def test_format_with_microseconds(self):
        # Microseconds should be ignored
        dt = datetime(2026, 3, 15, 10, 20, 30, 123456, tzinfo=timezone.utc)
        assert _format_timestamp(dt) == "20260315T102030Z"


class TestEnvBuildIdPrecedence:
    """Test that env BUILD_ID has highest precedence."""

    def test_env_build_id_overrides_everything(self, monkeypatch, tmp_path):
        # Create a build file
        build_file = tmp_path / ".build.json"
        build_file.write_text(json.dumps({
            "build_id": "file-build-id",
            "branch": "file-branch",
            "timestamp_utc": "20260101T000000Z",
        }))

        # Set env BUILD_ID
        monkeypatch.setenv("DEVLOGS_BUILD_ID", "env-build-id-override")
        monkeypatch.setenv("DEVLOGS_BRANCH", "env-branch")

        result = resolve_build_info(path=build_file, now_fn=fixed_now)

        assert result.build_id == "env-build-id-override"
        assert result.branch == "env-branch"
        assert result.source == "env"
        assert result.path is None  # No file path when from env

    def test_env_build_id_without_other_env_vars(self, monkeypatch):
        monkeypatch.setenv("DEVLOGS_BUILD_ID", "direct-build-id")
        # Clear other vars
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)
        monkeypatch.delenv("DEVLOGS_BUILD_TIMESTAMP_UTC", raising=False)

        result = resolve_build_info(now_fn=fixed_now)

        assert result.build_id == "direct-build-id"
        assert result.branch is None
        assert result.timestamp_utc == FIXED_TIMESTAMP
        assert result.source == "env"


class TestEnvBranchAndTimestamp:
    """Test env provides branch and timestamp (build_id computed)."""

    def test_env_branch_generates_build_id(self, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.setenv("DEVLOGS_BRANCH", "feature/my-feature")

        result = resolve_build_info(now_fn=fixed_now)

        assert result.build_id == f"feature/my-feature-{FIXED_TIMESTAMP}"
        assert result.branch == "feature/my-feature"
        assert result.timestamp_utc == FIXED_TIMESTAMP
        assert result.source == "env"

    def test_env_timestamp_used(self, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.setenv("DEVLOGS_BRANCH", "main")
        monkeypatch.setenv("DEVLOGS_BUILD_TIMESTAMP_UTC", "20250101T120000Z")

        result = resolve_build_info(now_fn=fixed_now)

        assert result.build_id == "main-20250101T120000Z"
        assert result.timestamp_utc == "20250101T120000Z"
        assert result.source == "env"

    def test_custom_env_prefix(self, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.setenv("MYAPP_BUILD_ID", "custom-prefix-id")

        result = resolve_build_info(env_prefix="MYAPP_", now_fn=fixed_now)

        assert result.build_id == "custom-prefix-id"
        assert result.source == "env"


class TestFileProvidesBuildInfo:
    """Test file provides build info."""

    def test_file_provides_all_fields(self, tmp_path, monkeypatch):
        # Clear env vars
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)
        monkeypatch.delenv("DEVLOGS_BUILD_TIMESTAMP_UTC", raising=False)

        build_file = tmp_path / ".build.json"
        build_file.write_text(json.dumps({
            "build_id": "file-build-123",
            "branch": "develop",
            "timestamp_utc": "20260115T093000Z",
        }))

        result = resolve_build_info(path=build_file, now_fn=fixed_now)

        assert result.build_id == "file-build-123"
        assert result.branch == "develop"
        assert result.timestamp_utc == "20260115T093000Z"
        assert result.source == "file"
        assert result.path == str(build_file)

    def test_file_with_extra_keys(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)

        build_file = tmp_path / ".build.json"
        build_file.write_text(json.dumps({
            "build_id": "build-with-extras",
            "branch": "main",
            "timestamp_utc": "20260115T093000Z",
            "commit": "abc123",
            "pipeline_id": "12345",
            "custom_field": "value",
        }))

        result = resolve_build_info(path=build_file, now_fn=fixed_now)

        assert result.build_id == "build-with-extras"
        assert result.branch == "main"
        assert result.source == "file"


class TestEnvOverridesFile:
    """Test that env can override individual fields from file."""

    def test_env_branch_overrides_file_branch(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.setenv("DEVLOGS_BRANCH", "env-branch-override")

        build_file = tmp_path / ".build.json"
        build_file.write_text(json.dumps({
            "build_id": "file-build-id",
            "branch": "file-branch",
            "timestamp_utc": "20260115T093000Z",
        }))

        result = resolve_build_info(path=build_file, now_fn=fixed_now)

        # build_id from file, but branch overridden by env
        assert result.build_id == "file-build-id"
        assert result.branch == "env-branch-override"
        assert result.source == "file"

    def test_env_timestamp_overrides_file_timestamp(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)
        monkeypatch.setenv("DEVLOGS_BUILD_TIMESTAMP_UTC", "20250505T555555Z")

        build_file = tmp_path / ".build.json"
        build_file.write_text(json.dumps({
            "build_id": "file-build-id",
            "branch": "main",
            "timestamp_utc": "20260115T093000Z",
        }))

        result = resolve_build_info(path=build_file, now_fn=fixed_now)

        assert result.build_id == "file-build-id"
        assert result.timestamp_utc == "20250505T555555Z"
        assert result.source == "file"


class TestInvalidFile:
    """Test that invalid JSON file is ignored and fallback is used."""

    def test_invalid_json_falls_back_to_generated(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)

        build_file = tmp_path / ".build.json"
        build_file.write_text("{ invalid json }")

        result = resolve_build_info(path=build_file, now_fn=fixed_now)

        assert result.build_id == f"unknown-{FIXED_TIMESTAMP}"
        assert result.source == "generated"

    def test_file_not_dict_falls_back(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)

        build_file = tmp_path / ".build.json"
        build_file.write_text(json.dumps(["not", "a", "dict"]))

        result = resolve_build_info(path=build_file, now_fn=fixed_now)

        assert result.build_id == f"unknown-{FIXED_TIMESTAMP}"
        assert result.source == "generated"

    def test_file_missing_build_id_falls_back(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)

        build_file = tmp_path / ".build.json"
        build_file.write_text(json.dumps({
            "branch": "main",
            "timestamp_utc": "20260115T093000Z",
            # No build_id!
        }))

        result = resolve_build_info(path=build_file, now_fn=fixed_now)

        # Falls back to generated
        assert result.build_id == f"unknown-{FIXED_TIMESTAMP}"
        assert result.source == "generated"

    def test_nonexistent_file_generates(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)

        nonexistent = tmp_path / "does-not-exist.json"

        result = resolve_build_info(path=nonexistent, now_fn=fixed_now)

        assert result.build_id == f"unknown-{FIXED_TIMESTAMP}"
        assert result.source == "generated"


class TestWriteIfMissing:
    """Test write_if_missing=True writes a valid JSON file."""

    def test_writes_file_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)
        monkeypatch.chdir(tmp_path)

        result = resolve_build_info(write_if_missing=True, now_fn=fixed_now)

        # Check the file was written
        expected_path = tmp_path / DEFAULT_BUILD_INFO_FILENAME
        assert expected_path.exists()
        assert result.path == str(expected_path)

        # Verify file contents
        with open(expected_path) as f:
            data = json.load(f)
        assert data["build_id"] == f"unknown-{FIXED_TIMESTAMP}"
        assert data["branch"] is None
        assert data["timestamp_utc"] == FIXED_TIMESTAMP

    def test_does_not_overwrite_existing_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)

        # Create existing file
        build_file = tmp_path / ".build.json"
        original_content = {
            "build_id": "existing-build-id",
            "branch": "existing-branch",
            "timestamp_utc": "20250101T000000Z",
        }
        build_file.write_text(json.dumps(original_content))

        result = resolve_build_info(path=build_file, write_if_missing=True, now_fn=fixed_now)

        # Should use existing file
        assert result.build_id == "existing-build-id"
        assert result.source == "file"

        # File should not be modified
        with open(build_file) as f:
            data = json.load(f)
        assert data == original_content

    def test_write_failure_does_not_raise(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)

        # Try to write to a read-only directory
        read_only_dir = tmp_path / "readonly"
        read_only_dir.mkdir()

        # Change to a writable directory but specify path in readonly
        monkeypatch.chdir(tmp_path)

        # Mock the write to fail
        with mock.patch("devlogs.build_info._write_build_info_file", return_value=False):
            # Should not raise
            result = resolve_build_info(write_if_missing=True, now_fn=fixed_now)

        assert result.build_id == f"unknown-{FIXED_TIMESTAMP}"
        assert result.source == "generated"


class TestAllowGitFalse:
    """Test that allow_git=False never calls git."""

    def test_no_subprocess_called_when_allow_git_false(self, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)

        # Mock subprocess.run to track if it's called
        original_run = subprocess.run
        subprocess_called = False

        def mock_run(*args, **kwargs):
            nonlocal subprocess_called
            subprocess_called = True
            return original_run(*args, **kwargs)

        with mock.patch("devlogs.build_info.subprocess.run", side_effect=mock_run):
            result = resolve_build_info(allow_git=False, now_fn=fixed_now)

        assert not subprocess_called
        assert result.branch is None
        assert result.source == "generated"


class TestAllowGitTrue:
    """Test allow_git=True behavior with various git scenarios."""

    def test_git_success_gets_branch(self, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)

        mock_result = mock.Mock()
        mock_result.returncode = 0
        mock_result.stdout = "feature/test-branch\n"

        with mock.patch("devlogs.build_info.subprocess.run", return_value=mock_result):
            result = resolve_build_info(allow_git=True, now_fn=fixed_now)

        assert result.branch == "feature/test-branch"
        assert result.build_id == f"feature/test-branch-{FIXED_TIMESTAMP}"

    def test_git_command_not_found(self, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)

        with mock.patch("devlogs.build_info.subprocess.run", side_effect=FileNotFoundError()):
            result = resolve_build_info(allow_git=True, now_fn=fixed_now)

        assert result.branch is None
        assert result.build_id == f"unknown-{FIXED_TIMESTAMP}"

    def test_git_nonzero_exit(self, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)

        mock_result = mock.Mock()
        mock_result.returncode = 128
        mock_result.stdout = ""

        with mock.patch("devlogs.build_info.subprocess.run", return_value=mock_result):
            result = resolve_build_info(allow_git=True, now_fn=fixed_now)

        assert result.branch is None
        assert result.build_id == f"unknown-{FIXED_TIMESTAMP}"

    def test_git_timeout(self, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)

        with mock.patch("devlogs.build_info.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 5)):
            result = resolve_build_info(allow_git=True, now_fn=fixed_now)

        assert result.branch is None
        assert result.build_id == f"unknown-{FIXED_TIMESTAMP}"

    def test_git_returns_HEAD_detached(self, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)

        mock_result = mock.Mock()
        mock_result.returncode = 0
        mock_result.stdout = "HEAD\n"  # Detached HEAD state

        with mock.patch("devlogs.build_info.subprocess.run", return_value=mock_result):
            result = resolve_build_info(allow_git=True, now_fn=fixed_now)

        # Should treat HEAD as no branch
        assert result.branch is None
        assert result.build_id == f"unknown-{FIXED_TIMESTAMP}"


class TestDeterministicBuildId:
    """Test that build_id is deterministic via injected now_fn."""

    def test_same_now_fn_gives_same_result(self, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)

        result1 = resolve_build_info(now_fn=fixed_now)
        result2 = resolve_build_info(now_fn=fixed_now)

        assert result1.build_id == result2.build_id
        assert result1.timestamp_utc == result2.timestamp_utc

    def test_different_now_fn_gives_different_result(self, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)

        def other_now():
            return datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

        result1 = resolve_build_info(now_fn=fixed_now)
        result2 = resolve_build_info(now_fn=other_now)

        assert result1.build_id != result2.build_id
        assert result1.timestamp_utc == FIXED_TIMESTAMP
        assert result2.timestamp_utc == "20250615T120000Z"


class TestSearchUpBehavior:
    """Test that build info file is found in parent directories."""

    def test_finds_file_in_parent_directory(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)
        monkeypatch.delenv("DEVLOGS_BUILD_INFO_PATH", raising=False)

        # Create nested structure
        parent = tmp_path / "project"
        child = parent / "src" / "app"
        child.mkdir(parents=True)

        # Put build file in parent
        build_file = parent / ".build.json"
        build_file.write_text(json.dumps({
            "build_id": "parent-build-id",
            "branch": "main",
            "timestamp_utc": "20260115T093000Z",
        }))

        # Change to child directory
        monkeypatch.chdir(child)

        result = resolve_build_info(now_fn=fixed_now)

        assert result.build_id == "parent-build-id"
        assert result.source == "file"
        assert result.path == str(build_file)

    def test_stops_at_max_depth(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)
        monkeypatch.delenv("DEVLOGS_BUILD_INFO_PATH", raising=False)

        # Create deeply nested structure
        deep = tmp_path
        for i in range(15):
            deep = deep / f"level{i}"
        deep.mkdir(parents=True)

        # Put build file at root
        build_file = tmp_path / ".build.json"
        build_file.write_text(json.dumps({
            "build_id": "root-build-id",
            "branch": "main",
            "timestamp_utc": "20260115T093000Z",
        }))

        # Change to deep directory
        monkeypatch.chdir(deep)

        # With small max_depth, should not find the file
        result = resolve_build_info(max_search_depth=3, now_fn=fixed_now)

        assert result.build_id == f"unknown-{FIXED_TIMESTAMP}"
        assert result.source == "generated"

    def test_env_build_info_path_override(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)

        # Create a build file in a non-standard location
        custom_dir = tmp_path / "custom" / "location"
        custom_dir.mkdir(parents=True)
        custom_file = custom_dir / "my-build.json"
        custom_file.write_text(json.dumps({
            "build_id": "custom-path-build-id",
            "branch": "custom",
            "timestamp_utc": "20260115T093000Z",
        }))

        monkeypatch.setenv("DEVLOGS_BUILD_INFO_PATH", str(custom_file))
        monkeypatch.chdir(tmp_path)

        result = resolve_build_info(now_fn=fixed_now)

        assert result.build_id == "custom-path-build-id"
        assert result.source == "file"


class TestResolveBuildId:
    """Test the resolve_build_id convenience function."""

    def test_returns_string_only(self, monkeypatch):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.delenv("DEVLOGS_BRANCH", raising=False)

        result = resolve_build_id(now_fn=fixed_now)

        assert isinstance(result, str)
        assert result == f"unknown-{FIXED_TIMESTAMP}"

    def test_passes_all_options(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DEVLOGS_BUILD_ID", raising=False)
        monkeypatch.setenv("MYAPP_BUILD_ID", "custom-id")

        result = resolve_build_id(env_prefix="MYAPP_", now_fn=fixed_now)

        assert result == "custom-id"


class TestGenerateBuildInfoFile:
    """Test the generate_build_info_file utility."""

    def test_generates_file_in_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        result = generate_build_info_file(now_fn=fixed_now, allow_git=False)

        assert result is not None
        assert result.exists()
        assert result.name == DEFAULT_BUILD_INFO_FILENAME

        with open(result) as f:
            data = json.load(f)
        assert data["build_id"] == f"unknown-{FIXED_TIMESTAMP}"
        assert data["timestamp_utc"] == FIXED_TIMESTAMP

    def test_generates_at_custom_path(self, tmp_path):
        custom_path = tmp_path / "build" / "info.json"

        result = generate_build_info_file(custom_path, now_fn=fixed_now, allow_git=False)

        assert result is not None
        assert result == custom_path
        assert custom_path.exists()

    def test_explicit_branch(self, tmp_path):
        output = tmp_path / ".build.json"

        result = generate_build_info_file(output, branch="release/v1.0", now_fn=fixed_now)

        assert result is not None
        with open(result) as f:
            data = json.load(f)
        assert data["branch"] == "release/v1.0"
        assert data["build_id"] == f"release/v1.0-{FIXED_TIMESTAMP}"

    def test_uses_git_when_allowed(self, tmp_path):
        output = tmp_path / ".build.json"

        mock_result = mock.Mock()
        mock_result.returncode = 0
        mock_result.stdout = "develop\n"

        with mock.patch("devlogs.build_info.subprocess.run", return_value=mock_result):
            result = generate_build_info_file(output, allow_git=True, now_fn=fixed_now)

        assert result is not None
        with open(result) as f:
            data = json.load(f)
        assert data["branch"] == "develop"


class TestBuildInfoDataclass:
    """Test BuildInfo dataclass."""

    def test_dataclass_fields(self):
        bi = BuildInfo(
            build_id="test-id",
            branch="main",
            timestamp_utc="20260124T000000Z",
            source="file",
            path="/path/to/file",
        )

        assert bi.build_id == "test-id"
        assert bi.branch == "main"
        assert bi.timestamp_utc == "20260124T000000Z"
        assert bi.source == "file"
        assert bi.path == "/path/to/file"

    def test_branch_can_be_none(self):
        bi = BuildInfo(
            build_id="test-id",
            branch=None,
            timestamp_utc="20260124T000000Z",
            source="generated",
            path=None,
        )

        assert bi.branch is None
        assert bi.path is None


class TestReadBuildInfoFile:
    """Test _read_build_info_file helper."""

    def test_reads_valid_file(self, tmp_path):
        build_file = tmp_path / ".build.json"
        build_file.write_text(json.dumps({"build_id": "test", "branch": "main"}))

        result = _read_build_info_file(build_file)

        assert result == {"build_id": "test", "branch": "main"}

    def test_returns_none_for_invalid_json(self, tmp_path):
        build_file = tmp_path / ".build.json"
        build_file.write_text("not json")

        result = _read_build_info_file(build_file)

        assert result is None

    def test_returns_none_for_nonexistent_file(self, tmp_path):
        result = _read_build_info_file(tmp_path / "nonexistent.json")

        assert result is None

    def test_returns_none_for_non_dict(self, tmp_path):
        build_file = tmp_path / ".build.json"
        build_file.write_text(json.dumps(["list", "not", "dict"]))

        result = _read_build_info_file(build_file)

        assert result is None


class TestFindBuildInfoFile:
    """Test _find_build_info_file helper."""

    def test_explicit_path_exists(self, tmp_path):
        build_file = tmp_path / "custom.json"
        build_file.write_text("{}")

        result = _find_build_info_file(build_file, ".build.json", 10)

        assert result == build_file

    def test_explicit_path_not_exists(self, tmp_path):
        result = _find_build_info_file(tmp_path / "nonexistent.json", ".build.json", 10)

        assert result is None

    def test_env_override_path(self, tmp_path, monkeypatch):
        custom_file = tmp_path / "env-specified.json"
        custom_file.write_text("{}")
        monkeypatch.setenv("DEVLOGS_BUILD_INFO_PATH", str(custom_file))

        result = _find_build_info_file(None, ".build.json", 10)

        assert result == custom_file


class TestGetGitBranch:
    """Test _get_git_branch helper."""

    def test_returns_branch_on_success(self):
        mock_result = mock.Mock()
        mock_result.returncode = 0
        mock_result.stdout = "main\n"

        with mock.patch("devlogs.build_info.subprocess.run", return_value=mock_result):
            result = _get_git_branch()

        assert result == "main"

    def test_returns_none_on_failure(self):
        with mock.patch("devlogs.build_info.subprocess.run", side_effect=FileNotFoundError()):
            result = _get_git_branch()

        assert result is None

    def test_returns_none_for_empty_output(self):
        mock_result = mock.Mock()
        mock_result.returncode = 0
        mock_result.stdout = "\n"

        with mock.patch("devlogs.build_info.subprocess.run", return_value=mock_result):
            result = _get_git_branch()

        assert result is None
