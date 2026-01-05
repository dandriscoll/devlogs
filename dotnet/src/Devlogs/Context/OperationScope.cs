namespace Devlogs.Context;

/// <summary>
/// Represents a disposable operation scope that restores the previous context when disposed.
/// </summary>
internal sealed class OperationScope : IDisposable
{
    private readonly DevlogsContext _context;
    private readonly string? _previousOperationId;
    private readonly string? _previousArea;
    private bool _disposed;

    public OperationScope(
        DevlogsContext context,
        string? operationId,
        string? area)
    {
        _context = context ?? throw new ArgumentNullException(nameof(context));

        // Save previous values
        _previousOperationId = _context.GetOperationId();
        _previousArea = _context.GetArea();

        // Set new values
        _context.SetOperationIdInternal(operationId ?? Guid.NewGuid().ToString());

        if (area != null)
        {
            _context.SetArea(area);
        }
    }

    public void Dispose()
    {
        if (_disposed)
            return;

        _disposed = true;

        // Restore previous values
        _context.SetOperationIdInternal(_previousOperationId);
        _context.SetArea(_previousArea);
    }
}
