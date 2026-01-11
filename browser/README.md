# devlogs-browser

Browser logging library for DevLogs - forwards console logs to OpenSearch.

## Installation

```bash
npm install devlogs-browser
```

## Usage

```javascript
import * as devlogs from 'devlogs-browser';

devlogs.init({
  url: 'http://admin:admin@localhost:9200',
  index: 'devlogs-myapp',
  area: 'frontend'
});

// Now console.log/warn/error/info are forwarded to OpenSearch
console.log('Hello from browser!');
```

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
