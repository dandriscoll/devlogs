namespace Devlogs.Configuration;

/// <summary>
/// Configuration options for Devlogs.
/// </summary>
public sealed class DevlogsOptions
{
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
