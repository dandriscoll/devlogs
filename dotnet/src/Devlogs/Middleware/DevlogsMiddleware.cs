using Microsoft.AspNetCore.Http;
using Devlogs.Context;

namespace Devlogs.Middleware;

/// <summary>
/// Middleware that automatically creates operation scopes for HTTP requests.
/// </summary>
public sealed class DevlogsMiddleware
{
    private readonly RequestDelegate _next;
    private readonly string _defaultArea;

    /// <summary>
    /// Initializes a new instance of the DevlogsMiddleware.
    /// </summary>
    /// <param name="next">The next middleware in the pipeline.</param>
    /// <param name="defaultArea">The default area name for web requests.</param>
    public DevlogsMiddleware(RequestDelegate next, string defaultArea = "web")
    {
        _next = next ?? throw new ArgumentNullException(nameof(next));
        _defaultArea = defaultArea;
    }

    /// <summary>
    /// Invokes the middleware.
    /// </summary>
    public async Task InvokeAsync(HttpContext context, IDevlogsContext devlogsContext)
    {
        if (context == null)
            throw new ArgumentNullException(nameof(context));
        if (devlogsContext == null)
            throw new ArgumentNullException(nameof(devlogsContext));

        // Generate operation ID from trace identifier or create new GUID
        var operationId = context.TraceIdentifier ?? Guid.NewGuid().ToString();

        // Create operation scope for this request
        using (devlogsContext.BeginOperation(operationId, _defaultArea))
        {
            await _next(context);
        }
    }
}
