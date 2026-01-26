# Devlogs Record Format (v2.0)

The devlogs record format defines a standardized structure for log records submitted to the devlogs collector and used by the DevlogsHandler. This document describes the schema fields, their meanings, and usage guidelines.

## Schema Overview

```
+---------------------------------------------------------------------------+
|                          Devlogs Record v2.0                               |
+---------------------------------------------------------------------------+
| REQUIRED:                                                                  |
|   application     string    The emitting application name                  |
|   component       string    Component/module within application            |
|   timestamp       string    ISO 8601 timestamp when event occurred         |
+---------------------------------------------------------------------------+
| TOP-LEVEL LOG FIELDS (optional):                                           |
|   message         string    Human-readable log message                     |
|   level           string    Log level (debug, info, warning, error, etc.)  |
|   area            string    Functional area or category                    |
+---------------------------------------------------------------------------+
| OPTIONAL METADATA:                                                         |
|   environment     string    Deployment environment                         |
|   version         string    Application version                            |
|   operation_id    string    Request/operation correlation ID               |
|   fields          object    Custom nested JSON data                        |
+---------------------------------------------------------------------------+
| COLLECTOR-SET (added during ingestion):                                    |
|   collected_ts    string    ISO 8601 timestamp when received               |
|   client_ip       string    Submitting client's IP address                 |
|   identity        object    Identity resolved from auth token              |
+---------------------------------------------------------------------------+
```

## Required Fields

### application

**Type:** string (non-empty)

The name of the application emitting the log. This should be a stable identifier that doesn't change between deployments.

**Guidelines:**
- Use lowercase with hyphens: `my-web-app`, `payment-service`
- Keep it short but descriptive
- Should be consistent across all components of the same application
- Don't include environment or version in the name

**Examples:**
- `api-gateway`
- `user-service`
- `background-worker`

### component

**Type:** string (non-empty)

The component or module within the application that generated the log. This provides finer-grained identification within a larger application.

**Guidelines:**
- Use lowercase with hyphens
- Can be hierarchical: `auth`, `auth.oauth`, `auth.oauth.google`
- Should map to logical parts of your codebase
- Can be dynamic (e.g., worker ID) if needed

**Examples:**
- `api`
- `database`
- `queue-processor`
- `http-handler`

### timestamp

**Type:** string (ISO 8601 format)

The timestamp when the event occurred at the source. This is the "wall clock" time when the log was generated, before any network delays.

**Format:** ISO 8601 with timezone

**Accepted formats:**
- `2024-01-15T10:30:00Z` (UTC with Z suffix)
- `2024-01-15T10:30:00.123Z` (with milliseconds)
- `2024-01-15T10:30:00+00:00` (with offset)
- `2024-01-15T10:30:00+0000` (offset without colon)

**Guidelines:**
- Always use UTC for consistency
- Include milliseconds for high-frequency logging
- Set this at the point of logging, not when sending

## Top-Level Log Fields

These fields are promoted to the top level for easier querying and consistent structure.

### message

**Type:** string or null

Human-readable description of the log event. This should be clear and concise.

**Examples:**
- `User login successful`
- `Payment processed`
- `Database connection failed`

### level

**Type:** string or null

The log level indicating severity. Normalized to lowercase.

**Standard values:**
| Level | Use For |
|-------|---------|
| `debug` | Detailed debugging information |
| `info` | Normal operations, confirmations |
| `warning` | Unexpected but handled situations |
| `error` | Errors that need attention |
| `critical` | System-wide failures |

### area

**Type:** string or null

Functional area or category of the log. Useful for filtering logs by business domain.

**Examples:**
- `auth` - Authentication/authorization
- `billing` - Payment and billing
- `notifications` - Email, SMS, push notifications
- `sync` - Data synchronization

## Optional Metadata Fields

### environment

**Type:** string or null

The deployment environment where the application is running.

**Common values:**
- `development` or `dev`
- `staging`
- `production` or `prod`
- `test`

**Guidelines:**
- Use consistent naming across all applications
- Set this globally in your client configuration
- Useful for filtering logs by environment

### version

**Type:** string or null

The version of the application emitting the log.

**Common formats:**
- Semantic versioning: `1.2.3`, `2.0.0-beta.1`
- Build ID: `build-12345`
- Git SHA: `abc123def`
- Branch-timestamp: `main-20240115T103000Z`

### operation_id

**Type:** string or null

Correlation ID for tracing requests across services. Useful for distributed tracing.

**Guidelines:**
- Use UUIDs or unique strings
- Propagate across service boundaries
- Include in all logs for the same request

### fields

**Type:** object (arbitrary nested JSON) or null

Custom data associated with the log event. This is where application-specific information goes.

**Guidelines:**
- Use this for custom data beyond the standard fields
- Structure is arbitrary - nest as deeply as needed
- Keep field names consistent across your application
- Consider using common field names:
  - `user_id` - authenticated user
  - `request_id` - request correlation ID
  - `duration_ms` - operation timing
  - `error` - error details

**Example:**
```json
{
  "fields": {
    "user_id": "user-123",
    "request": {
      "method": "POST",
      "path": "/api/auth/login",
      "ip": "192.168.1.100"
    },
    "metrics": {
      "duration_ms": 45,
      "db_queries": 2
    }
  }
}
```

## Collector-Set Fields

These fields are automatically added by the collector during ingestion. Do not include them in your payload.

### collected_ts

**Type:** string (ISO 8601 format)

The timestamp when the collector received the record. This can be compared with `timestamp` to measure ingestion latency.

### client_ip

**Type:** string

The IP address of the client that submitted the log. The collector checks:
1. `X-Forwarded-For` header (first IP in chain)
2. `X-Real-IP` header
3. Direct connection IP

### identity

**Type:** object

Identity information resolved from the authentication token. Every record includes an identity with one of three modes:

#### Anonymous Mode

No verified identity. Used when no token is provided or token is not recognized.

```json
{"identity": {"mode": "anonymous"}}
```

#### Verified Mode

Identity resolved from the token-to-identity mapping (`DEVLOGS_TOKEN_MAP_KV`).

```json
{
  "identity": {
    "mode": "verified",
    "id": "service-1",
    "name": "My Service",
    "type": "service",
    "tags": {"team": "backend", "env": "prod"}
  }
}
```

Fields:
- `mode`: Always "verified"
- `id`: Required identifier from token mapping
- `name`: Optional display name
- `type`: Optional type (e.g., "service", "user", "ci")
- `tags`: Optional key-value metadata

#### Passthrough Mode

Identity preserved from the payload. Used in `require_token_passthrough` auth mode when the payload includes an `identity` object.

```json
{
  "identity": {
    "mode": "passthrough",
    "custom_id": "abc",
    "role": "admin"
  }
}
```

The passthrough mode preserves any custom fields from the original payload identity, plus adds `"mode": "passthrough"`.

## Examples

### Minimal Record

```json
{
  "application": "my-app",
  "component": "api",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Standard Log Record

```json
{
  "application": "my-app",
  "component": "api",
  "timestamp": "2024-01-15T10:30:00Z",
  "message": "User logged in successfully",
  "level": "info",
  "area": "auth"
}
```

### Full Record

```json
{
  "application": "payment-service",
  "component": "stripe-handler",
  "timestamp": "2024-01-15T10:30:00.123Z",
  "message": "Payment processed successfully",
  "level": "info",
  "area": "billing",
  "environment": "production",
  "version": "2.1.0",
  "operation_id": "req-abc123",
  "fields": {
    "transaction_id": "txn_abc123",
    "amount_cents": 5000,
    "currency": "USD",
    "customer": {
      "id": "cus_xyz789",
      "email": "user@example.com"
    },
    "timing": {
      "stripe_api_ms": 234,
      "total_ms": 256
    }
  }
}
```

### Batch Payload

```json
{
  "records": [
    {
      "application": "my-app",
      "component": "api",
      "timestamp": "2024-01-15T10:30:00Z",
      "message": "Request started",
      "level": "debug"
    },
    {
      "application": "my-app",
      "component": "api",
      "timestamp": "2024-01-15T10:30:00.050Z",
      "message": "Request completed",
      "level": "info"
    }
  ]
}
```

## Validation Rules

The collector enforces these validation rules:

1. **application**: Required, must be non-empty string
2. **component**: Required, must be non-empty string
3. **timestamp**: Required, must be valid ISO 8601 timestamp
4. **message**: Optional, must be string if provided
5. **level**: Optional, must be string if provided
6. **area**: Optional, must be string if provided
7. **environment**: Optional, must be string if provided
8. **version**: Optional, must be string if provided
9. **fields**: Optional, must be object (dict) if provided

### Error Response

When validation fails:

```json
{
  "code": "VALIDATION_FAILED",
  "subcode": "MISSING_FIELD",
  "message": "Missing required field: component"
}
```

For batch requests, the error includes the record index:

```json
{
  "code": "VALIDATION_FAILED",
  "subcode": "INVALID_TIMESTAMP",
  "message": "Record 2: Field 'timestamp' must be ISO 8601 format"
}
```

## Best Practices

### Naming Conventions

| Field | Convention | Example |
|-------|-----------|---------|
| application | lowercase-hyphen | `user-service` |
| component | lowercase-hyphen or dot-separated | `api.auth` |
| environment | lowercase | `production` |
| version | semver or build-id | `1.2.3` |
| field keys | snake_case | `user_id`, `request_path` |

### Timestamp Handling

- Generate timestamps at log creation time, not send time
- Use UTC consistently
- Include milliseconds for high-frequency logging
- Compare `timestamp` and `collected_ts` to monitor ingestion latency

### Custom Fields Structure

Organize your `fields` object consistently:

```json
{
  "fields": {
    "context": {
      "user_id": "...",
      "session_id": "...",
      "request_id": "..."
    },

    "data": {
      "operation_specific": "values",
      "go": "here"
    },

    "metrics": {
      "duration_ms": 45,
      "count": 10
    },

    "error": {
      "type": "ValidationError",
      "message": "Invalid input",
      "stack": "..."
    }
  }
}
```
