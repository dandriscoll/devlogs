using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Devlogs.Client;
using Devlogs.Configuration;
using Devlogs.Context;
using Devlogs.Formatting;

namespace Devlogs.Provider;

/// <summary>
/// Logger provider that creates DevlogsLogger instances.
/// </summary>
public sealed class DevlogsLoggerProvider : ILoggerProvider
{
    private readonly IOpenSearchClient _client;
    private readonly LogDocumentFormatter _formatter;
    private readonly string _indexName;

    public DevlogsLoggerProvider(
        IOptions<DevlogsOptions> options,
        IDevlogsContext? context = null)
    {
        if (options == null)
            throw new ArgumentNullException(nameof(options));

        var opts = options.Value;

        // Create OpenSearch client
        _client = new LightweightOpenSearchClient(
            opts.OpenSearchHost,
            opts.OpenSearchPort,
            opts.OpenSearchUser,
            opts.OpenSearchPassword,
            opts.OpenSearchTimeout);

        // Create context if not provided
        var devlogsContext = context ?? new DevlogsContext();

        // Create formatter
        _formatter = new LogDocumentFormatter(devlogsContext);

        _indexName = opts.IndexName;
    }

    public ILogger CreateLogger(string categoryName)
    {
        return new DevlogsLogger(categoryName, _client, _formatter, _indexName);
    }

    public void Dispose()
    {
        // Nothing to dispose
    }
}
