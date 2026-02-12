# devlogs-browser

Browser logging library for DevLogs - forwards console logs to OpenSearch or a collector endpoint.

## How It Works

devlogs-browser captures logs by **intercepting `console.log`, `console.warn`, `console.error`, `console.debug`, and `console.info`**. After calling `init()`, every console call is wrapped: the original method is called first (so browser DevTools still work normally), then the log entry is formatted and sent to your configured backend via `fetch`.

This means:

- Any code that calls `console.error("something failed")` will automatically have that error captured and forwarded.
- Code that handles errors silently (e.g. a `catch` block that calls `setState()` but never `console.error()`) will **not** be captured. Add a `console.error()` call to make those visible.
- Uncaught exceptions and unhandled promise rejections are **not** captured by default because they don't go through `console.*`. Call `installGlobalHandlers()` after `init()` to capture these automatically.

## Installation

```bash
npm install devlogs-browser
```

## Quick Start

```javascript
import * as devlogs from 'devlogs-browser';

devlogs.init({
  url: 'http://admin:admin@localhost:9200',
  index: 'devlogs-myapp',
  application: 'my-frontend',
  component: 'dashboard',
  area: 'frontend'
});

// Capture uncaught errors and unhandled promise rejections
devlogs.installGlobalHandlers();

// Now all console output and uncaught errors are forwarded
console.log('Hello from browser!');
```

## Usage

### OpenSearch mode (direct)

```javascript
import * as devlogs from 'devlogs-browser';

devlogs.init({
  url: 'http://admin:admin@localhost:9200',
  index: 'devlogs-myapp',
  application: 'my-frontend',
  component: 'dashboard',
  area: 'frontend'
});

// Now console.log/warn/error/info are forwarded to OpenSearch
console.log('Hello from browser!');
```

### Collector mode

```javascript
import * as devlogs from 'devlogs-browser';

devlogs.init({
  url: 'https://mytoken@collector.example.com',
  application: 'my-frontend',
  component: 'dashboard',
  area: 'frontend'
});

// Logs are sent to the collector with Bearer token auth
console.log('Hello via collector!');
```

### URL format detection

The mode is auto-detected from the URL:

- `http://user:pass@host:port` — OpenSearch mode (Basic auth)
- `https://token@host:port` — Collector mode (Bearer token)
- `https://host:port` — Collector mode (no auth)
- `opensearch://` / `opensearchs://` — Force OpenSearch mode

### Capturing uncaught errors

By default, devlogs only captures explicit `console.*` calls. To also capture uncaught exceptions and unhandled promise rejections, call `installGlobalHandlers()` after `init()`:

```javascript
devlogs.init({ url: '...', application: 'my-app', component: 'ui' });
devlogs.installGlobalHandlers();

// These are now captured:
// - Uncaught throw new Error('oops')
// - Unhandled Promise.reject('failed')
```

The global handlers use `addEventListener`, so they won't interfere with any existing `window.onerror` or `window.onunhandledrejection` handlers in your application. They are automatically removed when you call `destroy()`.

## Production Deployment

Devlogs is a development tool and should not run in production:

### Option 1: Conditional initialization

```javascript
if (process.env.NODE_ENV === 'development') {
  devlogs.init({ url: '...', application: '...', component: '...' });
  devlogs.installGlobalHandlers();
}
```

### Option 2: Don't import at all

Only import devlogs in development - bundlers will tree-shake it out of production builds.

## API

- `init(options)` - Initialize and intercept console methods
- `destroy()` - Restore original console methods and remove global handlers
- `installGlobalHandlers()` - Capture uncaught errors and unhandled promise rejections (call after `init()`)
- `setArea(area)` - Set the current area
- `setOperationId(id)` - Set the current operation ID
- `withOperation(id, fn)` - Run function with temporary operation context
- `setFields(fields)` - Set custom fields to include in all logs
