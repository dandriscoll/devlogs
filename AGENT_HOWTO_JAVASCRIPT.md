# JavaScript / TypeScript (browser): Language-Specific Notes

See the [main README](README.md#javascript--typescript-browser) for the copy/paste agent prompt.

- **How it works**: `devlogs.init()` intercepts `console.log`, `console.warn`, `console.error`, `console.debug`, and `console.info`. Each call is forwarded to your backend while the original console output is preserved for browser DevTools.
- **`installGlobalHandlers()`** registers `window` event listeners for `error` (uncaught exceptions) and `unhandledrejection` (unhandled promise rejections). Without this, errors that never pass through `console.error()` — such as an unhandled `throw` or a rejected promise with no `.catch()` — will not be captured.
- **Silent catch blocks**: code that catches an error and handles it without calling `console.error()` (e.g. `catch (e) { setErrorState(e) }`) will not be captured. Add a `console.error(e)` in those blocks to make the error visible to devlogs.
- **URL auto-detection**: the URL format determines the connection mode:
  - `http://user:pass@host:port` — OpenSearch direct (Basic auth)
  - `https://token@host:port` — Collector (Bearer token)
  - `https://host:port` — Collector (no auth)
- **Custom fields**: pass a plain object as the last argument to any `console.*` call. It will be merged into the log document's `fields` property:
  ```javascript
  console.log('Loaded page', { route: '/dashboard', loadTime: 230 });
  ```
- **Context helpers**: `setArea(area)`, `setOperationId(id)`, and `withOperation(id, fn)` tag all subsequent logs with area/operation metadata for filtering.
- **No runtime dependencies**: `devlogs-browser` uses only native browser APIs (`fetch`, `URL`). Bundle size is ~16KB before minification.
- **Production safety**: wrap `init()` in an environment check or don't import the package at all — bundlers will tree-shake it out.
