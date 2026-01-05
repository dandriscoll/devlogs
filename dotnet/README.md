# Devlogs for .NET

A developer-focused logging library for .NET that ships logs to OpenSearch with operation correlation. This is the C# port of the Python devlogs library.

## Features

- ✅ **Microsoft.Extensions.Logging integration** - Works with ILogger
- ✅ **Operation correlation** - Track logs across an entire operation
- ✅ **Async-safe context** - Uses AsyncLocal for context management
- ✅ **Circuit breaker** - Prevents cascade failures when OpenSearch is unavailable
- ✅ **Structured logging** - Add custom features to log entries
- ✅ **ASP.NET Core middleware** - Auto-inject operation_id from HTTP requests
- ✅ **Lightweight** - Minimal dependencies, simple implementation

## Installation

```bash
dotnet add package Devlogs
```

## Quick Start

### 1. Configure in Program.cs

```csharp
using Devlogs.Configuration;
using Devlogs.Middleware;

var builder = WebApplication.CreateBuilder(args);

// Add Devlogs logger using appsettings.json
builder.Logging.AddDevlogs(builder.Configuration.GetSection("Devlogs"));

// Or configure in code
builder.Logging.AddDevlogs(options =>
{
    options.OpenSearchHost = "localhost";
    options.OpenSearchPort = 9200;
    options.OpenSearchUser = "admin";
    options.OpenSearchPassword = "admin";
    options.IndexName = "devlogs-myapp";
});

var app = builder.Build();

// Add middleware for automatic operation_id injection
app.UseDevlogs();

app.MapGet("/", (ILogger<Program> logger) =>
{
    logger.LogInformation("Hello from Devlogs!");
    return "Hello World!";
});

app.Run();
```

### 2. Configure appsettings.json

```json
{
  "Logging": {
    "LogLevel": {
      "Default": "Information"
    }
  },
  "Devlogs": {
    "OpenSearchHost": "localhost",
    "OpenSearchPort": 9200,
    "OpenSearchUser": "admin",
    "OpenSearchPassword": "admin",
    "IndexName": "devlogs-myapp"
  }
}
```

### 3. Use in your code

```csharp
public class OrderService
{
    private readonly ILogger<OrderService> _logger;
    private readonly IDevlogsContext _context;

    public OrderService(ILogger<OrderService> logger, IDevlogsContext context)
    {
        _logger = logger;
        _context = context;
    }

    public async Task ProcessOrder(string orderId)
    {
        // Create operation scope - all logs within this scope share the same operation_id
        using (_context.BeginOperation(orderId, "orders"))
        {
            _logger.LogInformation("Starting order processing");

            // ... do work ...

            _logger.LogInformation("Order processing completed");
        }
    }
}
```

## Advanced Usage

### Logging with Features (Structured Data)

Add custom structured data to your logs:

```csharp
using (_logger.BeginScope(new Dictionary<string, object>
{
    ["features"] = new Dictionary<string, object>
    {
        ["user_id"] = userId,
        ["plan"] = "premium",
        ["request_count"] = 42
    }
}))
{
    _logger.LogInformation("User action completed");
}
```

### Manual Operation Scopes

```csharp
public class BackgroundJobService
{
    private readonly IDevlogsContext _context;
    private readonly ILogger<BackgroundJobService> _logger;

    public async Task RunJob(string jobId)
    {
        // Create operation scope with custom operation_id and area
        using (_context.BeginOperation(jobId, "background-jobs"))
        {
            _logger.LogInformation("Job started");

            await DoWork();

            _logger.LogInformation("Job completed");
            // All logs here have the same operation_id and area
        }
    }
}
```

### Setting Area Without Operation Scope

```csharp
public class Startup
{
    public void Configure(IApplicationBuilder app, IDevlogsContext context)
    {
        // Set area for all subsequent logs in this context
        context.SetArea("startup");

        // This log will have area="startup"
        _logger.LogInformation("Application starting");
    }
}
```

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| OpenSearchHost | localhost | OpenSearch host address |
| OpenSearchPort | 9200 | OpenSearch port |
| OpenSearchUser | admin | Username for basic auth |
| OpenSearchPassword | admin | Password for basic auth |
| OpenSearchTimeout | 30 | HTTP timeout in seconds |
| IndexName | devlogs-0001 | OpenSearch index name |
| CircuitBreakerDurationSeconds | 60 | Circuit breaker open duration |
| ErrorPrintIntervalSeconds | 10 | Error message throttling interval |

## OpenSearch Document Schema

Each log entry is stored as a document in OpenSearch with the following structure:

```json
{
  "doc_type": "log_entry",
  "timestamp": "2024-01-04T12:34:56.789Z",
  "level": "info",
  "levelno": 2,
  "logger_name": "MyApp.Controllers.OrderController",
  "message": "Order processed successfully",
  "pathname": "/app/Controllers/OrderController.cs",
  "lineno": 42,
  "funcName": "ProcessOrder",
  "thread": 12345,
  "process": 6789,
  "exception": null,
  "area": "api",
  "operation_id": "abc-123-def-456",
  "features": {
    "user_id": 42,
    "order_total": 199.99
  }
}
```

## Circuit Breaker

The library includes a circuit breaker that prevents cascade failures when OpenSearch is unavailable:

- When indexing fails, the circuit opens for 60 seconds (configurable)
- During this time, log indexing is silently skipped (logs don't block your app)
- Error messages are throttled to print every 10 seconds (configurable)
- Circuit automatically closes on the next successful index operation

## Middleware

The `UseDevlogs()` middleware automatically creates an operation scope for each HTTP request:

- Operation ID is derived from `HttpContext.TraceIdentifier`
- Default area is "web" (configurable)
- All logs within the request share the same operation_id

```csharp
// Use default area ("web")
app.UseDevlogs();

// Use custom area
app.UseDevlogs("api");
```

## Testing

Run the unit tests:

```bash
cd /src/devlogs/dotnet
dotnet test
```

## Building the NuGet Package

```bash
cd /src/devlogs/dotnet/src/Devlogs
dotnet pack -c Release
```

The package will be created in `bin/Release/Devlogs.1.0.0.nupkg`.

## Comparison with Python Version

This C# library provides feature parity with the Python devlogs library:

| Feature | Python | C# (.NET) |
|---------|--------|-----------|
| Context management | contextvars.ContextVar | AsyncLocal<T> |
| Context manager | @contextmanager | IDisposable (using) |
| Handler integration | logging.Handler | ILogger/ILoggerProvider |
| Circuit breaker | ✅ | ✅ |
| Feature extraction | ✅ | ✅ |
| HTTP integration | Flask/FastAPI | ASP.NET Core middleware |
| Configuration | env vars + dotenv | appsettings.json + IConfiguration |

## Requirements

- .NET 8.0 or later
- OpenSearch 1.x or 2.x

## License

MIT License - same as the Python version

## Related Projects

- [Python devlogs](../../../README.md) - Original Python implementation
- [OpenSearch](https://opensearch.org/) - Search and analytics engine

## Support

For issues, questions, or contributions, please visit the [GitHub repository](https://github.com/thedandriscoll/devlogs).
