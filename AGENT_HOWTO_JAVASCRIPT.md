# Agent Instructions: JavaScript / TypeScript (browser)

Copy/paste the block below into your coding agent.

> Please do the following in this project:
> 1. Install the browser package as a dev dependency: `npm install --save-dev devlogs-browser`.
> 2. Initialize devlogs early in the application entrypoint, wrapped in an environment check so it only runs in development:
>    ```javascript
>    import * as devlogs from 'devlogs-browser';
>
>    if (process.env.NODE_ENV === 'development') {
>      devlogs.init({
>        url: 'https://admin:YourPasswordHere@localhost:9200',
>        index: 'devlogs-<projectname>',
>        application: 'my-app',   // Required: your app name
>        component: 'frontend',   // Required: component name
>      });
>      devlogs.installGlobalHandlers();
>    }
>    ```
> 3. Use `devlogs.setArea('dashboard')` and `devlogs.setOperationId('op-123')` to add context to logs. Pass a plain object as the last argument to attach custom fields:
>    ```javascript
>    console.log('User action', { userId: 123, action: 'clicked' });
>    ```

## Browser-specific notes

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
