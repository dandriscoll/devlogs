using Microsoft.Extensions.Logging;
using Devlogs.Client;
using Devlogs.Formatting;

namespace Devlogs.Provider;

/// <summary>
/// Logger implementation that ships logs to OpenSearch.
/// </summary>
internal sealed class DevlogsLogger : ILogger
{
    private readonly string _categoryName;
    private readonly IOpenSearchClient _client;
    private readonly LogDocumentFormatter _formatter;
    private readonly string _indexName;

    public DevlogsLogger(
        string categoryName,
        IOpenSearchClient client,
        LogDocumentFormatter formatter,
        string indexName)
    {
        _categoryName = categoryName ?? throw new ArgumentNullException(nameof(categoryName));
        _client = client ?? throw new ArgumentNullException(nameof(client));
        _formatter = formatter ?? throw new ArgumentNullException(nameof(formatter));
        _indexName = indexName ?? throw new ArgumentNullException(nameof(indexName));
    }

    public IDisposable? BeginScope<TState>(TState state) where TState : notnull
    {
        // Scope support is handled by the logging framework
        return null;
    }

    public bool IsEnabled(LogLevel logLevel)
    {
        // Always enabled (let OpenSearch filter if needed)
        return logLevel != LogLevel.None;
    }

    public void Log<TState>(
        LogLevel logLevel,
        EventId eventId,
        TState state,
        Exception? exception,
        Func<TState, Exception?, string> formatter)
    {
        if (!IsEnabled(logLevel))
            return;

        // Check circuit breaker
        if (CircuitBreaker.CircuitBreaker.IsOpen)
            return; // Silently fail

        try
        {
            var document = _formatter.FormatLogDocument(
                logLevel,
                eventId,
                state,
                exception,
                formatter,
                _categoryName);

            // Index document (fire and forget to avoid blocking logging)
            _ = Task.Run(async () =>
            {
                try
                {
                    var success = await _client.IndexAsync(_indexName, document);
                    if (success)
                    {
                        CircuitBreaker.CircuitBreaker.RecordSuccess();
                    }
                }
                catch (Exception ex)
                {
                    CircuitBreaker.CircuitBreaker.RecordFailure(ex);
                }
            });
        }
        catch (Exception ex)
        {
            CircuitBreaker.CircuitBreaker.RecordFailure(ex);
        }
    }
}
