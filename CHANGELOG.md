# Changelog

All notable changes to devlogs are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.4.5] - 2026-06-07

### Fixed
- `devlogs applications` now lists applications on existing indices. The
  `application` and `component` fields are queried via their `.keyword` subfield
  and are now mapped as keyword in the index template. Previously the aggregation
  ran against text-mapped fields, failed, and was silently swallowed — printing
  "No applications found." The `--application` and `--component` filters now also
  match multi-token values (e.g. `my-app`) on existing indices.

### Changed
- Query helpers (`list_applications`, `list_areas`, `list_operations`,
  `list_recent_operations`, `list_error_signatures`, `get_operation_summary`)
  now log failures (with stack info) instead of silently returning empty results.

### Security
- The OpenSearch client now applies TLS verification settings; the Loki proxy
  requires an admin token at startup.

### Added
- `Dockerfile.loki-proxy` bundling Loki with the proxy/collector in a single
  image (bash supervisor; write-ahead log on a persistent volume).

## Earlier releases

Release notes for v2.4.4 and earlier are published on the
[GitHub Releases](https://github.com/dandriscoll/devlogs/releases) page.
Version 2.0.0 introduced breaking changes — see [MIGRATION.md](MIGRATION.md).

[Unreleased]: https://github.com/dandriscoll/devlogs/compare/v2.4.5...HEAD
[2.4.5]: https://github.com/dandriscoll/devlogs/compare/v2.4.4...v2.4.5
