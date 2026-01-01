"""Tests for the levels module."""

import pytest

from devlogs.levels import normalize_level


class TestNormalizeLevel:
    """Tests for normalize_level function."""

    def test_none_returns_none(self):
        """Test None input returns None."""
        assert normalize_level(None) is None

    def test_lowercase_string_unchanged(self):
        """Test lowercase string is returned as-is."""
        assert normalize_level("debug") == "debug"
        assert normalize_level("info") == "info"
        assert normalize_level("warning") == "warning"
        assert normalize_level("error") == "error"
        assert normalize_level("critical") == "critical"

    def test_uppercase_converted_to_lowercase(self):
        """Test uppercase is converted to lowercase."""
        assert normalize_level("DEBUG") == "debug"
        assert normalize_level("INFO") == "info"
        assert normalize_level("WARNING") == "warning"
        assert normalize_level("ERROR") == "error"
        assert normalize_level("CRITICAL") == "critical"

    def test_mixed_case_converted_to_lowercase(self):
        """Test mixed case is converted to lowercase."""
        assert normalize_level("Debug") == "debug"
        assert normalize_level("InFo") == "info"
        assert normalize_level("WaRnInG") == "warning"

    def test_whitespace_stripped(self):
        """Test leading/trailing whitespace is stripped."""
        assert normalize_level("  debug") == "debug"
        assert normalize_level("debug  ") == "debug"
        assert normalize_level("  debug  ") == "debug"
        assert normalize_level("\tdebug\n") == "debug"

    def test_empty_string_returns_none(self):
        """Test empty string returns None."""
        assert normalize_level("") is None

    def test_whitespace_only_returns_none(self):
        """Test whitespace-only string returns None."""
        assert normalize_level("   ") is None
        assert normalize_level("\t\n") is None

    def test_non_string_converted_to_string(self):
        """Test non-string values are converted to string."""
        # Integer levels (like from logging module)
        assert normalize_level(10) == "10"  # DEBUG
        assert normalize_level(20) == "20"  # INFO
        assert normalize_level(30) == "30"  # WARNING

    def test_integer_with_string_repr(self):
        """Test integer-like values are handled."""
        assert normalize_level(0) == "0"
        assert normalize_level(100) == "100"

    def test_float_converted_to_string(self):
        """Test float values are converted to string."""
        assert normalize_level(10.0) == "10.0"

    def test_boolean_converted_to_string(self):
        """Test boolean values are converted to string."""
        assert normalize_level(True) == "true"
        assert normalize_level(False) == "false"

    def test_custom_level_names(self):
        """Test custom/non-standard level names work."""
        assert normalize_level("TRACE") == "trace"
        assert normalize_level("FATAL") == "fatal"
        assert normalize_level("NOTICE") == "notice"

    def test_level_with_numbers(self):
        """Test level names containing numbers."""
        assert normalize_level("debug1") == "debug1"
        assert normalize_level("ERROR2") == "error2"

    def test_unicode_levels(self):
        """Test unicode level names."""
        assert normalize_level("dbug") == "dbug"
        # Unicode characters should pass through
        assert normalize_level("INFO") == "info"
