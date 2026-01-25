namespace Devlogs.BuildInfo;

/// <summary>
/// Options for resolving build info.
/// </summary>
public sealed class BuildInfoOptions
{
    /// <summary>
    /// Explicit path to the build info file. If null, searches upward from current directory.
    /// </summary>
    public string? Path { get; set; }

    /// <summary>
    /// Filename to search for.
    /// </summary>
    public string Filename { get; set; } = ".build.json";

    /// <summary>
    /// Environment variable prefix.
    /// </summary>
    public string EnvPrefix { get; set; } = "DEVLOGS_";

    /// <summary>
    /// Enable git commands as fallback for branch detection.
    /// </summary>
    public bool AllowGit { get; set; }

    /// <summary>
    /// Custom function to get current time (for testing). If null, uses DateTime.UtcNow.
    /// </summary>
    public Func<DateTime>? NowFn { get; set; }

    /// <summary>
    /// Write the build info file if not found.
    /// </summary>
    public bool WriteIfMissing { get; set; }

    /// <summary>
    /// Maximum parent directories to search.
    /// </summary>
    public int MaxSearchDepth { get; set; } = 10;

    /// <summary>
    /// Custom environment variable getter (for testing).
    /// </summary>
    public Func<string, string?>? GetEnvironmentVariable { get; set; }
}
