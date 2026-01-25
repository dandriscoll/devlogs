using System.Diagnostics;
using System.Text.Json;

namespace Devlogs.BuildInfo;

/// <summary>
/// Resolves build information from file, environment, or generates it.
/// </summary>
public static class BuildInfoResolver
{
    private const string DefaultFilename = ".build.json";
    private const string DefaultEnvPrefix = "DEVLOGS_";
    private const int DefaultMaxSearchDepth = 10;

    /// <summary>
    /// Format a DateTime as compact ISO-like UTC timestamp: YYYYMMDDTHHMMSSZ.
    /// </summary>
    public static string FormatTimestamp(DateTime dateTime)
    {
        var utc = dateTime.Kind == DateTimeKind.Utc ? dateTime : dateTime.ToUniversalTime();
        return utc.ToString("yyyyMMdd'T'HHmmss'Z'");
    }

    /// <summary>
    /// Resolve build information from file, environment, or generate it.
    /// </summary>
    /// <param name="options">Configuration options. If null, uses defaults.</param>
    /// <returns>Resolved build info. Never returns null.</returns>
    /// <remarks>
    /// Priority order:
    /// 1. Environment variable BUILD_ID (if set) takes highest precedence
    /// 2. Build info file (if found and valid)
    /// 3. Environment variables for branch/timestamp
    /// 4. Git (if AllowGit=true)
    /// 5. Generated values
    /// </remarks>
    public static BuildInfo Resolve(BuildInfoOptions? options = null)
    {
        options ??= new BuildInfoOptions();

        var filename = string.IsNullOrEmpty(options.Filename) ? DefaultFilename : options.Filename;
        var envPrefix = string.IsNullOrEmpty(options.EnvPrefix) ? DefaultEnvPrefix : options.EnvPrefix;
        var maxSearchDepth = options.MaxSearchDepth <= 0 ? DefaultMaxSearchDepth : options.MaxSearchDepth;
        var nowFn = options.NowFn ?? (() => DateTime.UtcNow);
        var getEnv = options.GetEnvironmentVariable ?? Environment.GetEnvironmentVariable;

        // Environment variable names
        var envBuildId = $"{envPrefix}BUILD_ID";
        var envBranch = $"{envPrefix}BRANCH";
        var envTimestamp = $"{envPrefix}BUILD_TIMESTAMP_UTC";

        // Check for direct BUILD_ID env override (highest precedence)
        var directBuildId = getEnv(envBuildId);
        if (!string.IsNullOrEmpty(directBuildId))
        {
            var branch = getEnv(envBranch);
            var timestamp = getEnv(envTimestamp);
            if (string.IsNullOrEmpty(timestamp))
            {
                timestamp = FormatTimestamp(nowFn());
            }

            return new BuildInfo
            {
                BuildId = directBuildId,
                Branch = branch,
                TimestampUtc = timestamp,
                Source = BuildInfoSource.Env,
                Path = null
            };
        }

        // Try to find and read build info file
        var filePath = FindBuildInfoFile(options.Path, filename, maxSearchDepth, getEnv);
        BuildInfoFileData? fileData = null;
        if (!string.IsNullOrEmpty(filePath))
        {
            fileData = ReadBuildInfoFile(filePath);
        }

        if (fileData != null && !string.IsNullOrEmpty(fileData.BuildId))
        {
            // File found and valid - use its data
            // Allow env overrides for individual fields
            var branch = getEnv(envBranch);
            if (string.IsNullOrEmpty(branch))
            {
                branch = fileData.Branch;
            }

            var timestamp = getEnv(envTimestamp);
            if (string.IsNullOrEmpty(timestamp))
            {
                timestamp = fileData.TimestampUtc;
            }
            if (string.IsNullOrEmpty(timestamp))
            {
                timestamp = FormatTimestamp(nowFn());
            }

            return new BuildInfo
            {
                BuildId = fileData.BuildId,
                Branch = branch,
                TimestampUtc = timestamp,
                Source = BuildInfoSource.File,
                Path = filePath
            };
        }

        // Check if env provides branch and/or timestamp
        var envBranchValue = getEnv(envBranch);
        var envTimestampValue = getEnv(envTimestamp);

        // Determine branch
        string? resolvedBranch = null;
        if (!string.IsNullOrEmpty(envBranchValue))
        {
            resolvedBranch = envBranchValue;
        }
        else if (options.AllowGit)
        {
            resolvedBranch = GetGitBranch();
        }

        // Determine timestamp
        string resolvedTimestamp;
        if (!string.IsNullOrEmpty(envTimestampValue))
        {
            resolvedTimestamp = envTimestampValue;
        }
        else
        {
            resolvedTimestamp = FormatTimestamp(nowFn());
        }

        // Generate build_id
        var branchForId = resolvedBranch ?? "unknown";
        var buildId = $"{branchForId}-{resolvedTimestamp}";

        // Determine source
        var source = (!string.IsNullOrEmpty(envBranchValue) || !string.IsNullOrEmpty(envTimestampValue))
            ? BuildInfoSource.Env
            : BuildInfoSource.Generated;

        var result = new BuildInfo
        {
            BuildId = buildId,
            Branch = resolvedBranch,
            TimestampUtc = resolvedTimestamp,
            Source = source,
            Path = filePath
        };

        // Optionally write to file
        if (options.WriteIfMissing && fileData == null)
        {
            var writePath = filePath;
            if (string.IsNullOrEmpty(writePath))
            {
                writePath = System.IO.Path.Combine(Directory.GetCurrentDirectory(), filename);
            }

            if (WriteBuildInfoFile(writePath, result))
            {
                result = result with { Path = writePath };
            }
        }

        return result;
    }

    /// <summary>
    /// Convenience method that returns only the build_id string.
    /// </summary>
    public static string ResolveBuildId(BuildInfoOptions? options = null)
    {
        return Resolve(options).BuildId;
    }

    /// <summary>
    /// Generate a .build.json file for use at runtime.
    /// </summary>
    /// <param name="outputPath">Where to write the file. Defaults to current directory/.build.json.</param>
    /// <param name="branch">Explicit branch name. If null and allowGit=true, uses git.</param>
    /// <param name="allowGit">If true, attempts to get branch from git.</param>
    /// <param name="nowFn">Custom function to get current time (for testing).</param>
    /// <returns>Path to written file, or null if write failed.</returns>
    public static string? GenerateBuildInfoFile(
        string? outputPath = null,
        string? branch = null,
        bool allowGit = true,
        Func<DateTime>? nowFn = null)
    {
        nowFn ??= () => DateTime.UtcNow;

        if (string.IsNullOrEmpty(outputPath))
        {
            outputPath = System.IO.Path.Combine(Directory.GetCurrentDirectory(), DefaultFilename);
        }

        // Determine branch
        if (string.IsNullOrEmpty(branch) && allowGit)
        {
            branch = GetGitBranch();
        }

        var timestamp = FormatTimestamp(nowFn());
        var branchForId = branch ?? "unknown";
        var buildId = $"{branchForId}-{timestamp}";

        var info = new BuildInfo
        {
            BuildId = buildId,
            Branch = branch,
            TimestampUtc = timestamp,
            Source = BuildInfoSource.Generated,
            Path = outputPath
        };

        return WriteBuildInfoFile(outputPath, info) ? outputPath : null;
    }

    private static string? FindBuildInfoFile(
        string? explicitPath,
        string filename,
        int maxDepth,
        Func<string, string?> getEnv)
    {
        // Check env override first
        var envPath = getEnv($"{DefaultEnvPrefix}BUILD_INFO_PATH");
        if (!string.IsNullOrEmpty(envPath) && File.Exists(envPath))
        {
            return envPath;
        }

        if (!string.IsNullOrEmpty(explicitPath))
        {
            return File.Exists(explicitPath) ? explicitPath : null;
        }

        // Search upward from current directory
        var current = new DirectoryInfo(Directory.GetCurrentDirectory());
        for (var i = 0; i < maxDepth && current != null; i++)
        {
            var candidate = System.IO.Path.Combine(current.FullName, filename);
            if (File.Exists(candidate))
            {
                return candidate;
            }
            current = current.Parent;
        }

        return null;
    }

    private static BuildInfoFileData? ReadBuildInfoFile(string path)
    {
        try
        {
            var json = File.ReadAllText(path);
            var data = JsonSerializer.Deserialize<BuildInfoFileData>(json, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            });
            return data;
        }
        catch
        {
            return null;
        }
    }

    private static bool WriteBuildInfoFile(string path, BuildInfo info)
    {
        try
        {
            var dir = System.IO.Path.GetDirectoryName(path);
            if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
            {
                Directory.CreateDirectory(dir);
            }

            var data = new BuildInfoFileData
            {
                BuildId = info.BuildId,
                Branch = info.Branch,
                TimestampUtc = info.TimestampUtc
            };

            var json = JsonSerializer.Serialize(data, new JsonSerializerOptions
            {
                WriteIndented = true,
                PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower
            });

            File.WriteAllText(path, json + "\n");
            return true;
        }
        catch
        {
            return false;
        }
    }

    private static string? GetGitBranch()
    {
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = "git",
                Arguments = "rev-parse --abbrev-ref HEAD",
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };

            using var process = Process.Start(psi);
            if (process == null)
            {
                return null;
            }

            var output = process.StandardOutput.ReadToEnd().Trim();
            process.WaitForExit(5000);

            if (process.ExitCode == 0 && !string.IsNullOrEmpty(output) && output != "HEAD")
            {
                return output;
            }
        }
        catch
        {
            // Git not available or command failed
        }

        return null;
    }

    private sealed class BuildInfoFileData
    {
        public string? BuildId { get; set; }
        public string? Branch { get; set; }
        public string? TimestampUtc { get; set; }
    }
}
