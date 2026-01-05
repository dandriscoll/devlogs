namespace Devlogs.Client;

/// <summary>
/// Interface for OpenSearch client operations.
/// </summary>
public interface IOpenSearchClient
{
    /// <summary>
    /// Indexes a document in OpenSearch.
    /// </summary>
    /// <param name="indexName">The name of the index.</param>
    /// <param name="document">The document to index.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>True if successful, false otherwise.</returns>
    Task<bool> IndexAsync(string indexName, object document, CancellationToken cancellationToken = default);
}
