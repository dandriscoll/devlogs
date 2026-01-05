namespace Devlogs.Context;

/// <summary>
/// Provides context management for operation correlation across log entries.
/// </summary>
public interface IDevlogsContext
{
    /// <summary>
    /// Gets the current operation ID from the context.
    /// </summary>
    /// <returns>The operation ID, or null if not set.</returns>
    string? GetOperationId();

    /// <summary>
    /// Gets the current area from the context.
    /// </summary>
    /// <returns>The area name, or null if not set.</returns>
    string? GetArea();

    /// <summary>
    /// Sets the area for the current context.
    /// </summary>
    /// <param name="area">The area name to set.</param>
    void SetArea(string? area);

    /// <summary>
    /// Begins a new operation scope with optional operation ID and area.
    /// </summary>
    /// <param name="operationId">The operation ID. If null, a new GUID will be generated.</param>
    /// <param name="area">The area name. If null, the current area will be preserved.</param>
    /// <returns>A disposable scope that restores the previous context when disposed.</returns>
    IDisposable BeginOperation(string? operationId = null, string? area = null);
}
