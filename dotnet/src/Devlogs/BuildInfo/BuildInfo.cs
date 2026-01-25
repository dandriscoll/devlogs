namespace Devlogs.BuildInfo;

/// <summary>
/// Source of the build info.
/// </summary>
public enum BuildInfoSource
{
    /// <summary>Build info was read from a file.</summary>
    File,
    /// <summary>Build info was provided via environment variables.</summary>
    Env,
    /// <summary>Build info was generated at runtime.</summary>
    Generated
}

/// <summary>
/// Build information resolved from file, environment, or generated.
/// </summary>
public sealed class BuildInfo
{
    /// <summary>
    /// Unique build identifier (always non-empty).
    /// </summary>
    public string BuildId { get; init; } = string.Empty;

    /// <summary>
    /// Git branch name, if available.
    /// </summary>
    public string? Branch { get; init; }

    /// <summary>
    /// UTC timestamp in format YYYYMMDDTHHMMSSZ.
    /// </summary>
    public string TimestampUtc { get; init; } = string.Empty;

    /// <summary>
    /// Source of the build info.
    /// </summary>
    public BuildInfoSource Source { get; init; }

    /// <summary>
    /// File path used for build info, if any.
    /// </summary>
    public string? Path { get; init; }
}
