# Tests for schema detection and migration

import pytest
from devlogs.opensearch.mappings import (
	detect_schema_version,
	get_schema_issues,
	build_reindex_script,
	SCHEMA_VERSION,
)


class TestDetectSchemaVersion:
	def test_empty_mapping_returns_none(self):
		assert detect_schema_version({}) is None
		assert detect_schema_version(None) is None

	def test_v2_schema_detected(self):
		mapping = {
			"properties": {
				"timestamp": {"type": "date"},
				"level": {"type": "keyword"},
				"message": {"type": "text"},
				"logger": {"type": "keyword"},
				"funcname": {"type": "keyword"},
				"fields": {"type": "object"},
				"process": {"type": "integer"},
				"thread": {"type": "long"},
			}
		}
		assert detect_schema_version(mapping) == 2

	def test_v1_schema_with_logger_name_detected(self):
		mapping = {
			"properties": {
				"timestamp": {"type": "date"},
				"level": {"type": "keyword"},
				"message": {"type": "text"},
				"logger_name": {"type": "keyword"},
				"features": {"type": "object"},
			}
		}
		assert detect_schema_version(mapping) == 1

	def test_v1_schema_with_nested_source_detected(self):
		mapping = {
			"properties": {
				"timestamp": {"type": "date"},
				"level": {"type": "keyword"},
				"message": {"type": "text"},
				"source": {
					"type": "object",
					"properties": {
						"logger": {"type": "keyword"},
						"pathname": {"type": "keyword"},
					}
				},
			}
		}
		assert detect_schema_version(mapping) == 1

	def test_v1_schema_with_process_object_detected(self):
		mapping = {
			"properties": {
				"timestamp": {"type": "date"},
				"level": {"type": "keyword"},
				"message": {"type": "text"},
				"process": {
					"properties": {
						"id": {"type": "integer"},
						"thread": {"type": "long"},
					}
				},
			}
		}
		assert detect_schema_version(mapping) == 1

	def test_nested_mapping_format(self):
		"""Test detection with get_mapping response format."""
		mapping = {
			"my-index": {
				"mappings": {
					"properties": {
						"timestamp": {"type": "date"},
						"level": {"type": "keyword"},
						"logger": {"type": "keyword"},
						"funcname": {"type": "keyword"},
						"fields": {"type": "object"},
						"process": {"type": "integer"},
					}
				}
			}
		}
		assert detect_schema_version(mapping) == 2


class TestGetSchemaIssues:
	def test_no_issues_for_v2_schema(self):
		mapping = {
			"properties": {
				"logger": {"type": "keyword"},
				"funcname": {"type": "keyword"},
				"fields": {"type": "object"},
				"process": {"type": "integer"},
			}
		}
		issues = get_schema_issues(mapping)
		assert len(issues) == 0

	def test_reports_logger_name_issue(self):
		mapping = {
			"properties": {
				"logger_name": {"type": "keyword"},
			}
		}
		issues = get_schema_issues(mapping)
		assert any("logger_name" in issue for issue in issues)

	def test_reports_funcName_issue(self):
		mapping = {
			"properties": {
				"funcName": {"type": "keyword"},
			}
		}
		issues = get_schema_issues(mapping)
		assert any("funcName" in issue for issue in issues)

	def test_reports_features_issue(self):
		mapping = {
			"properties": {
				"features": {"type": "object"},
			}
		}
		issues = get_schema_issues(mapping)
		assert any("features" in issue for issue in issues)

	def test_reports_process_object_issue(self):
		mapping = {
			"properties": {
				"process": {
					"type": "object",
					"properties": {"id": {"type": "integer"}},
				},
			}
		}
		issues = get_schema_issues(mapping)
		assert any("process" in issue and "object" in issue for issue in issues)

	def test_reports_nested_source_issue(self):
		mapping = {
			"properties": {
				"source": {
					"type": "object",
					"properties": {"logger": {"type": "keyword"}},
				},
			}
		}
		issues = get_schema_issues(mapping)
		assert any("source" in issue for issue in issues)

	def test_reports_missing_v2_fields(self):
		mapping = {
			"properties": {
				"timestamp": {"type": "date"},
			}
		}
		issues = get_schema_issues(mapping)
		assert any("logger" in issue and "Missing" in issue for issue in issues)
		assert any("funcname" in issue and "Missing" in issue for issue in issues)
		assert any("fields" in issue and "Missing" in issue for issue in issues)


class TestBuildReindexScript:
	def test_script_is_valid_string(self):
		script = build_reindex_script()
		assert isinstance(script, str)
		assert len(script) > 0

	def test_script_handles_logger_name(self):
		script = build_reindex_script()
		assert "logger_name" in script
		assert "ctx._source.logger" in script

	def test_script_handles_funcName(self):
		script = build_reindex_script()
		assert "funcName" in script
		assert "funcname" in script

	def test_script_handles_features(self):
		script = build_reindex_script()
		assert "features" in script
		assert "fields" in script

	def test_script_handles_nested_source(self):
		script = build_reindex_script()
		assert "source" in script

	def test_script_handles_nested_process(self):
		script = build_reindex_script()
		assert "process" in script


class TestSchemaVersion:
	def test_current_version_is_2(self):
		assert SCHEMA_VERSION == 2
