# Python: Language-Specific Notes

See the [main README](README.md#python) for the copy/paste agent prompt.

- **DevlogsHandler** is a standard `logging.Handler`. It works with any Python logger — you can attach it to the root logger or to a specific named logger.
- **`get_opensearch_client()`** auto-discovers the connection from `.env.devlogs` or `DEVLOGS_URL` in the environment. No manual host/port/auth wiring needed.
- **`resolve_build_info(write_if_missing=True)`** generates a `.build.json` file on first run so every log entry carries a stable build ID. In CI, set `DEVLOGS_BUILD_ID` and `DEVLOGS_BRANCH` environment variables instead.
- **Conditional import** (`if os.getenv(...)`): by importing devlogs inside the guard, production environments never import the library at all. You can also make it an optional dependency:
  ```toml
  # pyproject.toml
  [project.optional-dependencies]
  dev = ["devlogs>=2.0.0"]
  ```
- **Structured fields**: pass extra data via the standard `extra` kwarg. A dict under `extra={"features": {...}}` is stored as the `fields` property in the log document:
  ```python
  logging.info("User signed in", extra={"features": {"user_id": 42}})
  ```
- **Context managers**: use `devlogs.context` to set `area` or `operation_id` for a block of code so every log within it is tagged automatically.
