# Changelog

All notable changes to the Devlogs Jenkins Plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-01-12

### Added
- Initial release of Devlogs Jenkins Plugin
- Pipeline step `devlogs` for wrapping build execution
- Real-time log streaming to OpenSearch/devlogs instances
- Per-pipeline URL configuration
- Automatic pass-through when no URL provided (no impact on builds)
- Batch processing of log entries (50 lines per batch)
- Error-resilient operation (logging failures don't cause build failures)
- Support for declarative and scripted pipelines
- Configuration UI with Jelly templates
- Comprehensive documentation and examples
- Unit tests with JenkinsRule

### Log Format
- Documents include: timestamp, run_id, job, build_number, build_url, seq, message, source, level
- Uses OpenSearch bulk API for efficient indexing
- Automatic sequence numbering for log ordering

### Known Limitations
- Log level is currently fixed at "info" (no automatic parsing of log levels)
- URL must include the index name (format: `https://user:pass@host:port/index`)
- Requires network access to OpenSearch from Jenkins agents

[Unreleased]: https://github.com/dandriscoll/devlogs/compare/jenkins-plugin-v1.0.0...HEAD
[1.0.0]: https://github.com/dandriscoll/devlogs/releases/tag/jenkins-plugin-v1.0.0
