# Agent Instructions: Python

Copy/paste the block below into your coding agent.

> Please do the following in this project:
> 1. Install `devlogs` as a dev dependency (`pip install devlogs` or add it to `requirements-dev.txt`/`pyproject.toml` optional dependencies).
> 2. Create a `.env.devlogs` file in the project root with a single `DEVLOGS_URL` variable (devlogs auto-discovers this file). Use the `opensearchs://` scheme for TLS or `opensearch://` for non-TLS:
>    ```
>    DEVLOGS_URL=opensearchs://admin:YourPasswordHere@localhost:9200/devlogs-<projectname>
>    ```
> 3. Run `devlogs init` (inside the virtualenv if one is set up) and verify the index is healthy.
> 4. Add devlogs hooks at the beginning of the application (main entrypoint/startup module), wrapped in an environment check so it only runs in development:
>    ```python
>    import os
>    import logging
>    if os.getenv("ENVIRONMENT") != "production":
>        from devlogs.handler import DevlogsHandler
>        from devlogs.opensearch.client import get_opensearch_client
>        from devlogs.build_info import resolve_build_info
>
>        build_info = resolve_build_info(write_if_missing=True)
>        handler = DevlogsHandler(
>            application="my-app",  # Required: your app name
>            component="api",       # Required: component name
>            level=logging.INFO,
>            opensearch_client=get_opensearch_client(),
>            version=build_info.build_id,
>        )
>        logging.getLogger().addHandler(handler)
>        logging.getLogger().setLevel(logging.INFO)
>        logging.info("App started")
>    ```
> 5. Ask the user if they want MCP set up; if yes, state which agent you are (`copilot`, `claude`, or `codex`) and run `devlogs initmcp <agent>`.

## Python-specific notes

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
