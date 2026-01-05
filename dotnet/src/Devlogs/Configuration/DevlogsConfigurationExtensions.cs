using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Devlogs.Context;
using Devlogs.Provider;

namespace Devlogs.Configuration;

/// <summary>
/// Extension methods for configuring Devlogs.
/// </summary>
public static class DevlogsConfigurationExtensions
{
    /// <summary>
    /// Adds Devlogs logger provider using configuration.
    /// </summary>
    /// <param name="builder">The logging builder.</param>
    /// <param name="configuration">Configuration section containing Devlogs options.</param>
    /// <returns>The logging builder for chaining.</returns>
    public static ILoggingBuilder AddDevlogs(
        this ILoggingBuilder builder,
        IConfiguration configuration)
    {
        if (builder == null)
            throw new ArgumentNullException(nameof(builder));
        if (configuration == null)
            throw new ArgumentNullException(nameof(configuration));

        // Register DevlogsContext as singleton
        builder.Services.AddSingleton<IDevlogsContext, DevlogsContext>();

        // Configure options from configuration
        builder.Services.Configure<DevlogsOptions>(configuration);

        // Add logger provider
        builder.Services.AddSingleton<ILoggerProvider, DevlogsLoggerProvider>();

        return builder;
    }

    /// <summary>
    /// Adds Devlogs logger provider using action-based configuration.
    /// </summary>
    /// <param name="builder">The logging builder.</param>
    /// <param name="configure">Action to configure Devlogs options.</param>
    /// <returns>The logging builder for chaining.</returns>
    public static ILoggingBuilder AddDevlogs(
        this ILoggingBuilder builder,
        Action<DevlogsOptions> configure)
    {
        if (builder == null)
            throw new ArgumentNullException(nameof(builder));
        if (configure == null)
            throw new ArgumentNullException(nameof(configure));

        // Register DevlogsContext as singleton
        builder.Services.AddSingleton<IDevlogsContext, DevlogsContext>();

        // Configure options using action
        builder.Services.Configure(configure);

        // Add logger provider
        builder.Services.AddSingleton<ILoggerProvider, DevlogsLoggerProvider>();

        return builder;
    }

    /// <summary>
    /// Adds Devlogs context to the service collection.
    /// </summary>
    /// <param name="services">The service collection.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddDevlogsContext(this IServiceCollection services)
    {
        if (services == null)
            throw new ArgumentNullException(nameof(services));

        services.AddSingleton<IDevlogsContext, DevlogsContext>();
        return services;
    }
}
