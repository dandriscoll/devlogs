using Microsoft.AspNetCore.Builder;

namespace Devlogs.Middleware;

/// <summary>
/// Extension methods for adding Devlogs middleware to the pipeline.
/// </summary>
public static class DevlogsMiddlewareExtensions
{
    /// <summary>
    /// Adds Devlogs middleware to the application pipeline.
    /// This creates an operation scope for each HTTP request.
    /// </summary>
    /// <param name="app">The application builder.</param>
    /// <param name="defaultArea">The default area name for web requests (default: "web").</param>
    /// <returns>The application builder for chaining.</returns>
    public static IApplicationBuilder UseDevlogs(
        this IApplicationBuilder app,
        string defaultArea = "web")
    {
        if (app == null)
            throw new ArgumentNullException(nameof(app));

        return app.UseMiddleware<DevlogsMiddleware>(defaultArea);
    }
}
