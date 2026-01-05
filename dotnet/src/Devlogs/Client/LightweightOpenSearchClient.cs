using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace Devlogs.Client;

/// <summary>
/// Lightweight OpenSearch client using HttpClient for indexing operations.
/// </summary>
public sealed class LightweightOpenSearchClient : IOpenSearchClient
{
    private readonly HttpClient _httpClient;
    private readonly string _baseUrl;

    /// <summary>
    /// Initializes a new instance of the LightweightOpenSearchClient.
    /// </summary>
    /// <param name="host">OpenSearch host.</param>
    /// <param name="port">OpenSearch port.</param>
    /// <param name="username">Username for basic authentication.</param>
    /// <param name="password">Password for basic authentication.</param>
    /// <param name="timeoutSeconds">HTTP request timeout in seconds.</param>
    public LightweightOpenSearchClient(
        string host,
        int port,
        string username,
        string password,
        int timeoutSeconds = 30)
    {
        _baseUrl = $"http://{host}:{port}";

        _httpClient = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(timeoutSeconds)
        };

        // Set up basic authentication
        var credentials = Convert.ToBase64String(Encoding.ASCII.GetBytes($"{username}:{password}"));
        _httpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Basic", credentials);
        _httpClient.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
    }

    /// <inheritdoc/>
    public async Task<bool> IndexAsync(string indexName, object document, CancellationToken cancellationToken = default)
    {
        try
        {
            var url = $"{_baseUrl}/{indexName}/_doc";
            var json = JsonSerializer.Serialize(document, new JsonSerializerOptions
            {
                PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
                DefaultIgnoreCondition = System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingNull
            });

            var content = new StringContent(json, Encoding.UTF8, "application/json");
            var response = await _httpClient.PostAsync(url, content, cancellationToken);

            if (response.StatusCode == HttpStatusCode.Unauthorized)
            {
                throw new AuthenticationFailedException("Authentication failed (HTTP 401)");
            }

            if (response.StatusCode == HttpStatusCode.NotFound)
            {
                throw new IndexNotFoundException($"Index '{indexName}' does not exist");
            }

            if (response.StatusCode == HttpStatusCode.BadRequest)
            {
                var errorBody = await response.Content.ReadAsStringAsync(cancellationToken);
                throw new QueryException($"Query error: Bad Request - {errorBody}");
            }

            response.EnsureSuccessStatusCode();
            return true;
        }
        catch (HttpRequestException ex)
        {
            throw new ConnectionFailedException($"Cannot connect to OpenSearch at {_baseUrl}", ex);
        }
        catch (TaskCanceledException ex)
        {
            throw new ConnectionFailedException($"Request to OpenSearch at {_baseUrl} timed out", ex);
        }
    }
}
