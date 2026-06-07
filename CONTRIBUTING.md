# Contributing to devlogs

Thanks for your interest in improving devlogs! Issues and pull requests are
welcome.

## Development setup

```sh
git clone https://github.com/dandriscoll/devlogs.git
cd devlogs
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # editable install with test deps
```

## Running tests

```sh
# Fast unit tests (no external services needed)
pytest -m "not integration"

# Integration tests need a running OpenSearch. The easiest local option:
docker compose up -d opensearch
DEVLOGS_OPENSEARCH_URL="opensearch://localhost:9200/devlogs-test" pytest -m integration
```

Integration tests `skip` automatically when no OpenSearch (or Loki) instance is
reachable, so the default `pytest` run is safe everywhere.

## Submitting a change

1. Open an issue first for anything non-trivial, so we can agree on the approach.
2. Branch from `main`, keep the change focused, and add or update tests —
   bug fixes should include a test that fails without the fix.
3. Run `pytest -m "not integration"` (and the integration suite if your change
   touches OpenSearch/query behavior) before opening the PR.
4. Match the surrounding style (the Python sources use tab indentation) and keep
   the README/`HOWTO-*` docs in sync if you change user-facing behavior.
5. Open the PR against `main` with a clear description of what changed and why.

## Reporting bugs

Use [GitHub issues](https://github.com/dandriscoll/devlogs/issues) for bugs and
feature requests. For **security** issues, do not open a public issue — follow
[SECURITY.md](SECURITY.md) instead.

## License

By contributing, you agree that your contributions are licensed under the
project's [MIT License](LICENSE).
