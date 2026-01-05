namespace Devlogs.CircuitBreaker;

/// <summary>
/// Circuit breaker to prevent cascade failures when OpenSearch is unavailable.
/// Uses static state shared across all logger instances.
/// </summary>
internal static class CircuitBreaker
{
    private static readonly object _lock = new();
    private static bool _isOpen;
    private static DateTimeOffset _openUntil = DateTimeOffset.MinValue;
    private static DateTimeOffset _lastErrorPrinted = DateTimeOffset.MinValue;

    private static readonly TimeSpan CircuitBreakerDuration = TimeSpan.FromSeconds(60);
    private static readonly TimeSpan ErrorPrintInterval = TimeSpan.FromSeconds(10);

    /// <summary>
    /// Checks if the circuit breaker is currently open.
    /// </summary>
    public static bool IsOpen
    {
        get
        {
            lock (_lock)
            {
                if (_isOpen && DateTimeOffset.UtcNow < _openUntil)
                {
                    return true;
                }

                // Circuit breaker timeout has passed, allow next attempt
                if (_isOpen && DateTimeOffset.UtcNow >= _openUntil)
                {
                    _isOpen = false;
                }

                return false;
            }
        }
    }

    /// <summary>
    /// Opens the circuit breaker after a failure.
    /// </summary>
    /// <param name="exception">The exception that caused the failure.</param>
    public static void RecordFailure(Exception exception)
    {
        lock (_lock)
        {
            var now = DateTimeOffset.UtcNow;

            _isOpen = true;
            _openUntil = now.Add(CircuitBreakerDuration);

            // Throttle error printing
            if (now - _lastErrorPrinted > ErrorPrintInterval)
            {
                Console.Error.WriteLine($"[devlogs] Failed to index log, pausing indexing for {CircuitBreakerDuration.TotalSeconds}s: {exception.Message}");
                _lastErrorPrinted = now;
            }
        }
    }

    /// <summary>
    /// Records a successful operation and closes the circuit if it was open.
    /// </summary>
    public static void RecordSuccess()
    {
        lock (_lock)
        {
            if (_isOpen)
            {
                _isOpen = false;
                _openUntil = DateTimeOffset.MinValue;
                Console.WriteLine("[devlogs] Connection restored, resuming indexing");
            }
        }
    }
}
