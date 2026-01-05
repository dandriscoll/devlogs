namespace Devlogs.Context;

/// <summary>
/// Default implementation of IDevlogsContext using AsyncLocal for async-safe context storage.
/// </summary>
public sealed class DevlogsContext : IDevlogsContext
{
    private static readonly AsyncLocal<string?> _operationId = new();
    private static readonly AsyncLocal<string?> _area = new();

    /// <inheritdoc/>
    public string? GetOperationId() => _operationId.Value;

    /// <inheritdoc/>
    public string? GetArea() => _area.Value;

    /// <inheritdoc/>
    public void SetArea(string? area)
    {
        _area.Value = area;
    }

    /// <summary>
    /// Internal method to set operation ID (used by OperationScope).
    /// </summary>
    internal void SetOperationIdInternal(string? operationId)
    {
        _operationId.Value = operationId;
    }

    /// <inheritdoc/>
    public IDisposable BeginOperation(string? operationId = null, string? area = null)
    {
        return new OperationScope(this, operationId, area);
    }
}
