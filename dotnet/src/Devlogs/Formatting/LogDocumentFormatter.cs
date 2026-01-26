using System.Diagnostics;
using System.Runtime.CompilerServices;
using Microsoft.Extensions.Logging;
using Devlogs.Context;
using Devlogs.Configuration;

namespace Devlogs.Formatting;

/// <summary>
/// Formats log events into OpenSearch document format (v2.0 schema).
/// </summary>
internal sealed class LogDocumentFormatter
{
    private readonly IDevlogsContext _context;
    private readonly DevlogsOptions _options;

    public LogDocumentFormatter(IDevlogsContext context, DevlogsOptions options)
    {
        _context = context ?? throw new ArgumentNullException(nameof(context));
        _options = options ?? throw new ArgumentNullException(nameof(options));
    }

    /// <summary>
    /// Formats a log event into an OpenSearch document using v2.0 schema.
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
            // Required fields
            ["application"] = _options.Application,
            ["component"] = _options.Component,
            ["timestamp"] = DateTime.UtcNow.ToString("o").Replace("+00:00", "Z"),
            // Top-level log fields
            ["message"] = formatter(state, exception),
            ["level"] = NormalizeLevel(logLevel),
            ["area"] = _context.GetArea(),
            // Optional metadata
            ["operation_id"] = _context.GetOperationId()
        };

        // Optional environment and version
        if (!string.IsNullOrEmpty(_options.Environment))
        {
            document["environment"] = _options.Environment;
        }
        if (!string.IsNullOrEmpty(_options.Version))
        {
            document["version"] = _options.Version;
        }

        // Source info (nested object)
        var source = new Dictionary<string, object?>
        {
            ["logger"] = categoryName
        };
        if (!string.IsNullOrEmpty(callerFilePath))
        {
            source["pathname"] = callerFilePath;
        }
        if (callerLineNumber > 0)
        {
            source["lineno"] = callerLineNumber;
        }
        if (!string.IsNullOrEmpty(callerMemberName))
        {
            source["funcName"] = callerMemberName;
        }
        document["source"] = source;

        // Process info (nested object)
        document["process"] = new Dictionary<string, object?>
        {
            ["id"] = Environment.ProcessId,
            ["thread"] = Environment.CurrentManagedThreadId
        };

        // Add exception if present
        if (exception != null)
        {
            document["exception"] = exception.ToString();
        }

        // Extract fields from state (renamed from features)
        var fields = FeatureExtractor.ExtractFeatures(state);
        if (fields != null && fields.Count > 0)
        {
            document["fields"] = fields;
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
