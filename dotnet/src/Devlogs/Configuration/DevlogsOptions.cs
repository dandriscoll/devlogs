namespace Devlogs.Configuration;

/// <summary>
/// Configuration options for Devlogs (v2.0).
/// </summary>
public sealed class DevlogsOptions
{
    /// <summary>
    /// Application name (required for v2.0 schema).
    /// </summary>
    public string Application { get; set; } = "unknown";

    /// <summary>
    /// Component name within the application (required for v2.0 schema).
    /// </summary>
    public string Component { get; set; } = "default";

    /// <summary>
    /// Deployment environment (e.g., 'development', 'production').
    /// </summary>
    public string? Environment { get; set; }

    /// <summary>
    /// Application version.
    /// </summary>
    public string? Version { get; set; }

    /// <summary>
    /// OpenSearch host address.
    /// </summary>
    public string OpenSearchHost { get; set; } = "localhost";

    /// <summary>
    /// OpenSearch port.
    /// </summary>
    public int OpenSearchPort { get; set; } = 9200;

    /// <summary>
    /// OpenSearch username for basic authentication.
    /// </summary>
    public string OpenSearchUser { get; set; } = "admin";

    /// <summary>
    /// OpenSearch password for basic authentication.
    /// </summary>
    public string OpenSearchPassword { get; set; } = "admin";

    /// <summary>
    /// HTTP request timeout in seconds.
    /// </summary>
    public int OpenSearchTimeout { get; set; } = 30;

    /// <summary>
    /// OpenSearch index name.
    /// </summary>
    public string IndexName { get; set; } = "devlogs-0001";

    /// <summary>
    /// Circuit breaker duration in seconds.
    /// </summary>
    public int CircuitBreakerDurationSeconds { get; set; } = 60;

    /// <summary>
    /// Error print interval in seconds.
    /// </summary>
    public int ErrorPrintIntervalSeconds { get; set; } = 10;
}
