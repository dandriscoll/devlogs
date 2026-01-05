namespace Devlogs.Client;

/// <summary>
/// Base exception for OpenSearch errors.
/// </summary>
public class OpenSearchException : Exception
{
    public OpenSearchException(string message) : base(message) { }
    public OpenSearchException(string message, Exception innerException) : base(message, innerException) { }
}

/// <summary>
/// Exception thrown when OpenSearch connection fails.
/// </summary>
public class ConnectionFailedException : OpenSearchException
{
    public ConnectionFailedException(string message) : base(message) { }
    public ConnectionFailedException(string message, Exception innerException) : base(message, innerException) { }
}

/// <summary>
/// Exception thrown when authentication to OpenSearch fails.
/// </summary>
public class AuthenticationFailedException : OpenSearchException
{
    public AuthenticationFailedException(string message) : base(message) { }
}

/// <summary>
/// Exception thrown when the specified index does not exist.
/// </summary>
public class IndexNotFoundException : OpenSearchException
{
    public IndexNotFoundException(string message) : base(message) { }
}

/// <summary>
/// Exception thrown when a query is malformed or invalid.
/// </summary>
public class QueryException : OpenSearchException
{
    public QueryException(string message) : base(message) { }
}
