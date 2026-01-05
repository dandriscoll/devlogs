using System.Diagnostics;
using System.Runtime.CompilerServices;
using Microsoft.Extensions.Logging;
using Devlogs.Context;

namespace Devlogs.Formatting;

/// <summary>
/// Formats log events into OpenSearch document format.
/// </summary>
internal sealed class LogDocumentFormatter
{
    private readonly IDevlogsContext _context;

    public LogDocumentFormatter(IDevlogsContext context)
    {
        _context = context ?? throw new ArgumentNullException(nameof(context));
    }

    /// <summary>
    /// Formats a log event into an OpenSearch document.
    /// </summary>
    public Dictionary<string, object?> FormatLogDocument<TState>(
        LogLevel logLevel,
        EventId eventId,
        TState state,
        Exception? exception,
        Func<TState, Exception?, string> formatter,
        string categoryName,
        [CallerFilePath] string? callerFilePath = null,
        [CallerLineNumber] int callerLineNumber = 0,
        [CallerMemberName] string? callerMemberName = null)
    {
        var document = new Dictionary<string, object?>
        {
            ["doc_type"] = "log_entry",
            ["timestamp"] = DateTime.UtcNow.ToString("o").Replace("+00:00", "Z"),
            ["level"] = NormalizeLevel(logLevel),
            ["levelno"] = (int)logLevel,
            ["logger_name"] = categoryName,
            ["message"] = formatter(state, exception),
            ["thread"] = Environment.CurrentManagedThreadId,
            ["process"] = Environment.ProcessId,
            ["area"] = _context.GetArea(),
            ["operation_id"] = _context.GetOperationId()
        };

        // Add caller information if available
        if (!string.IsNullOrEmpty(callerFilePath))
        {
            document["pathname"] = callerFilePath;
        }

        if (callerLineNumber > 0)
        {
            document["lineno"] = callerLineNumber;
        }

        if (!string.IsNullOrEmpty(callerMemberName))
        {
            document["funcName"] = callerMemberName;
        }

        // Add exception if present
        if (exception != null)
        {
            document["exception"] = exception.ToString();
        }

        // Extract features from state
        var features = FeatureExtractor.ExtractFeatures(state);
        if (features != null && features.Count > 0)
        {
            document["features"] = features;
        }

        return document;
    }

    /// <summary>
    /// Normalizes log level to lowercase string.
    /// </summary>
    private static string NormalizeLevel(LogLevel logLevel)
    {
        return logLevel switch
        {
            LogLevel.Trace => "trace",
            LogLevel.Debug => "debug",
            LogLevel.Information => "info",
            LogLevel.Warning => "warning",
            LogLevel.Error => "error",
            LogLevel.Critical => "critical",
            LogLevel.None => "none",
            _ => logLevel.ToString().ToLowerInvariant()
        };
    }
}
