# devlogs

<p align="center">
  <img src="https://raw.githubusercontent.com/dandriscoll/devlogs/main/devlogs.png" alt="devlogs logo" width="160">
</p>

<p align="center">
  <a href="https://pypi.org/project/devlogs/"><img src="https://img.shields.io/pypi/v/devlogs.svg" alt="PyPI version"></a>
  <a href="https://www.npmjs.com/package/devlogs-browser"><img src="https://img.shields.io/npm/v/devlogs-browser.svg" alt="npm version"></a>
  <a href="https://github.com/dandriscoll/devlogs/blob/main/LICENSE"><img src="https://img.shields.io/pypi/l/devlogs.svg" alt="License: MIT"></a>
</p>

**Let your AI coding agent read your app's logs and debug them for you — Python logging to OpenSearch, served over MCP.**

devlogs is a drop-in logging handler for your dev environment. It ships your
application's logs to [OpenSearch](https://opensearch.org/) and exposes them to
your coding agent (Claude, Copilot, Codex) over [MCP](https://modelcontextprotocol.io/),
so the agent can search your real runtime logs and fix problems on its own —
instead of you copy-pasting tracebacks back and forth.

- **Agent-native** — one command wires devlogs into Claude / Copilot / Codex; the agent queries your logs itself.
- **Drop-in** — a standard Python `logging.Handler` (plus a browser package, an HTTP collector, a Jenkins plugin, and a small web UI).
- **Dev-first** — guarded so it only runs in development; no production code paths changed.

> **Status:** actively developed and used; it's a development tool, not a
> production logging pipeline. See [Production deployment](#production-deployment).

---

## Quickstart — use it with your coding agent

**1. Install** (one line):

```sh
pip install devlogs
```

**2. Point devlogs at OpenSearch.** Don't have one? Stand up a local instance:

```sh
cp docker-compose.example.yaml docker-compose.yaml   # then set a password
docker compose up -d
```

**3. Paste this into your coding agent.** It installs devlogs as a dev
dependency, writes a connection config, initializes the index, and adds a
development-only logging hook to your entrypoint — without modifying your
existing code:

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

**4. Connect the agent and let it work:**

```sh
devlogs initmcp claude     # or: copilot | codex | all
devlogs tail -f            # watch logs yourself, or...
```

…then ask your agent to query devlogs for errors and watch it diagnose problems
from your real logs.

Working in the browser? See the [JavaScript / TypeScript setup](#javascript--typescript-browser).
Prefer wiring it up by hand? See [Manual setup](#manual-setup).

---

## How it works

```
your app  ──DevlogsHandler──▶  OpenSearch  ◀──MCP server──  your coding agent
(dev only)                     (your logs)                  (queries + debugs)
```

devlogs writes structured log records (the [Devlogs Record Format v2.0](https://github.com/dandriscoll/devlogs/blob/main/HOWTO-DEVLOGS-FORMAT.md):
`application`, `component`, `area`, `operation_id`, `level`, `message`, plus
arbitrary `fields`) to OpenSearch. The bundled MCP server lets your agent search,
tail, and summarize those records — by app, component, area, operation, or error.

---

## JavaScript / TypeScript (browser)

```sh
npm install --save-dev devlogs-browser
```

```javascript
import * as devlogs from 'devlogs-browser';

if (process.env.NODE_ENV === 'development') {
  devlogs.init({
    url: 'https://admin:YourPasswordHere@localhost:9200',
    index: 'devlogs-<projectname>',
    application: 'my-app',   // Required: your app name
    component: 'frontend',   // Required: component name
  });
  devlogs.installGlobalHandlers();
}

// console.* is now forwarded to OpenSearch; add context as needed:
devlogs.setArea('dashboard');
console.log('User action', { userId: 123, action: 'clicked' });
```

See [AGENT_HOWTO_JAVASCRIPT.md](https://github.com/dandriscoll/devlogs/blob/main/AGENT_HOWTO_JAVASCRIPT.md) for the agent paste-block and details.

---

## Manual setup

<details>
<summary>Wire it up by hand (Python)</summary>

1. **Install:** `pip install devlogs`
2. **Start OpenSearch:** `docker compose up -d opensearch` (or point `DEVLOGS_URL` at an existing cluster).
3. **Configure connection** (choose one):
   - `.env.devlogs` file (auto-discovered):
     ```
     DEVLOGS_URL=opensearchs://admin:YourPasswordHere@localhost:9200/devlogs-myproject
     ```
   - `--url` flag (no config file): `devlogs --url 'opensearchs://admin:pass@localhost:9200/devlogs-myproject' init`

   `devlogs mkurl` interactively builds a properly URL-encoded connection string (handy for passwords with special characters).
4. **Initialize indices/templates:** `devlogs init`
5. **Use in code (development only):**
   ```python
   import os, logging
   if os.getenv("ENVIRONMENT") != "production":
       from devlogs.handler import DevlogsHandler
       from devlogs.opensearch.client import get_opensearch_client
       from devlogs.build_info import resolve_build_info

       bi = resolve_build_info(write_if_missing=True)
       handler = DevlogsHandler(
           application="my-app", component="default",
           level=logging.DEBUG, opensearch_client=get_opensearch_client(),
           version=bi.build_id,
       )
       logging.getLogger().addHandler(handler)
       logging.getLogger().setLevel(logging.DEBUG)
       logging.info("Hello from devlogs!")
   ```
6. **Tail / search from the CLI:**
   ```sh
   devlogs tail --area web --follow
   devlogs search --q "error" --area web
   devlogs applications        # list apps that have logged
   ```
7. **Run the web UI:** `uvicorn devlogs.web.server:app --port 8088` → open `http://localhost:8088/ui/`

</details>

---

## Other ways to run it

- **MCP agent setup** — `devlogs initmcp copilot|claude|codex|all` writes the MCP config (`.mcp.json`, `.vscode/mcp.json`, or `~/.codex/config.toml`). See [HOWTO-MCP.md](https://github.com/dandriscoll/devlogs/blob/main/HOWTO-MCP.md).
- **HTTP collector** — a standalone ingest/forward service for centralized log collection: `devlogs-collector serve`. See [HOWTO-COLLECTOR.md](https://github.com/dandriscoll/devlogs/blob/main/HOWTO-COLLECTOR.md).
- **Jenkins** — stream build logs via the native plugin or a standalone binary. See [HOWTO-JENKINS.md](https://github.com/dandriscoll/devlogs/blob/main/HOWTO-JENKINS.md) and [jenkins-plugin/README.md](https://github.com/dandriscoll/devlogs/blob/main/jenkins-plugin/README.md).
- **Python collector client** — `from devlogs.devlogs_client import create_client`. See [HOWTO-COLLECTOR.md](https://github.com/dandriscoll/devlogs/blob/main/HOWTO-COLLECTOR.md).
- **Web UI** — a minimal embeddable log viewer. See [HOWTO-UI.md](https://github.com/dandriscoll/devlogs/blob/main/HOWTO-UI.md).

---

## Configuration

Connection (choose one):

- `DEVLOGS_URL` — standard connection URL with auto-detection. OpenSearch URLs (`opensearchs://`, `opensearch://`) connect directly; collector URLs (`http://`, `https://`) use the collector endpoint.
- Individual vars: `DEVLOGS_OPENSEARCH_HOST` / `_PORT` / `_USER` / `_PASS`, plus `DEVLOGS_OPENSEARCH_VERIFY_CERTS`, `DEVLOGS_OPENSEARCH_CA_CERT`.

Index & retention: `DEVLOGS_INDEX`, `DEVLOGS_RETENTION_DEBUG` / `_INFO` / `_WARNING` (e.g. `24h`, `7d`).

See [.env.example](https://github.com/dandriscoll/devlogs/blob/main/.env.example) for the full template and [HOWTO-CLI.md](https://github.com/dandriscoll/devlogs/blob/main/HOWTO-CLI.md) for the complete CLI reference (`--url`, `--env`, `mkurl`, and more).

---

## Production deployment

devlogs is a development tool. The examples above conditionally enable it with an
environment check; you can also make it an optional dependency:

```toml
# pyproject.toml
[project.optional-dependencies]
dev = ["devlogs>=2.0.0"]
```

Install with `pip install ".[dev]"` in development, `pip install .` in production.

---

## Documentation

- [HOWTO.md](https://github.com/dandriscoll/devlogs/blob/main/HOWTO.md) — integration guide
- [HOWTO-CLI.md](https://github.com/dandriscoll/devlogs/blob/main/HOWTO-CLI.md) — complete CLI reference
- [HOWTO-MCP.md](https://github.com/dandriscoll/devlogs/blob/main/HOWTO-MCP.md) — MCP agent setup
- [HOWTO-UI.md](https://github.com/dandriscoll/devlogs/blob/main/HOWTO-UI.md) — web UI guide
- [HOWTO-COLLECTOR.md](https://github.com/dandriscoll/devlogs/blob/main/HOWTO-COLLECTOR.md) — HTTP collector setup and deployment
- [HOWTO-DEVLOGS-FORMAT.md](https://github.com/dandriscoll/devlogs/blob/main/HOWTO-DEVLOGS-FORMAT.md) — record format reference
- [HOWTO-JENKINS.md](https://github.com/dandriscoll/devlogs/blob/main/HOWTO-JENKINS.md) — Jenkins setup
- [docs/build-info.md](https://github.com/dandriscoll/devlogs/blob/main/docs/build-info.md) — build-info helper guide
- [AGENT_HOWTO_PYTHON.md](https://github.com/dandriscoll/devlogs/blob/main/AGENT_HOWTO_PYTHON.md) / [AGENT_HOWTO_JAVASCRIPT.md](https://github.com/dandriscoll/devlogs/blob/main/AGENT_HOWTO_JAVASCRIPT.md) — agent setup blocks
- [MIGRATION.md](https://github.com/dandriscoll/devlogs/blob/main/MIGRATION.md) — upgrade guide (v2.0 introduced breaking changes)
- [CHANGELOG.md](https://github.com/dandriscoll/devlogs/blob/main/CHANGELOG.md) — release history

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](https://github.com/dandriscoll/devlogs/blob/main/CONTRIBUTING.md).
To report a security issue, please follow [SECURITY.md](https://github.com/dandriscoll/devlogs/blob/main/SECURITY.md) (do not open
a public issue).

## License

[MIT](https://github.com/dandriscoll/devlogs/blob/main/LICENSE).
