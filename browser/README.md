# devlogs-browser

Browser logging library for DevLogs - forwards console logs to OpenSearch or a collector endpoint.

## Installation

```bash
npm install devlogs-browser
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

## Production Deployment

Devlogs is a development tool and should not run in production:

### Option 1: Conditional initialization

```javascript
if (process.env.NODE_ENV === 'development') {
  devlogs.init({ url: '...', index: '...' });
}
```

### Option 2: Don't import at all

Only import devlogs in development - bundlers will tree-shake it out of production builds.

## API

- `init(options)` - Initialize and intercept console methods
- `destroy()` - Restore original console methods
- `setArea(area)` - Set the current area
- `setOperationId(id)` - Set the current operation ID
- `withOperation(fn, options)` - Run function with operation context
