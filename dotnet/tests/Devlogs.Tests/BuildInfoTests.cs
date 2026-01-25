using System.Text.Json;
using Devlogs.BuildInfo;
using Xunit;

namespace Devlogs.Tests;

public class BuildInfoTests
{
    // Fixed time for deterministic tests
    private static readonly DateTime FixedDateTime = new(2026, 1, 24, 15, 30, 45, DateTimeKind.Utc);
    private const string FixedTimestamp = "20260124T153045Z";

    private static DateTime FixedNow() => FixedDateTime;

    private static Func<string, string?> CreateEnvGetter(Dictionary<string, string>? env = null)
    {
        env ??= new Dictionary<string, string>();
        return key => env.TryGetValue(key, out var value) ? value : null;
    }

    public class FormatTimestampTests
    {
        [Fact]
        public void FormatsUtcDateTime()
        {
            var dt = new DateTime(2026, 3, 15, 10, 20, 30, DateTimeKind.Utc);
            Assert.Equal("20260315T102030Z", BuildInfoResolver.FormatTimestamp(dt));
        }

        [Fact]
        public void ConvertsLocalToUtc()
        {
            // Create a local time and verify it gets converted
            var local = new DateTime(2026, 3, 15, 10, 20, 30, DateTimeKind.Local);
            var result = BuildInfoResolver.FormatTimestamp(local);
            // Result should be a valid timestamp format
            Assert.Matches(@"^\d{8}T\d{6}Z$", result);
        }

        [Fact]
        public void PadsSingleDigits()
        {
            var dt = new DateTime(2026, 1, 5, 9, 8, 7, DateTimeKind.Utc);
            Assert.Equal("20260105T090807Z", BuildInfoResolver.FormatTimestamp(dt));
        }
    }

    public class EnvBuildIdPrecedenceTests
    {
        [Fact]
        public void EnvBuildIdOverridesEverything()
        {
            var tempDir = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
            Directory.CreateDirectory(tempDir);
            try
            {
                var buildFile = Path.Combine(tempDir, ".build.json");
                File.WriteAllText(buildFile, JsonSerializer.Serialize(new
                {
                    build_id = "file-build-id",
                    branch = "file-branch",
                    timestamp_utc = "20260101T000000Z"
                }));

                var env = new Dictionary<string, string>
                {
                    ["DEVLOGS_BUILD_ID"] = "env-build-id-override",
                    ["DEVLOGS_BRANCH"] = "env-branch"
                };

                var result = BuildInfoResolver.Resolve(new BuildInfoOptions
                {
                    Path = buildFile,
                    NowFn = FixedNow,
                    GetEnvironmentVariable = CreateEnvGetter(env)
                });

                Assert.Equal("env-build-id-override", result.BuildId);
                Assert.Equal("env-branch", result.Branch);
                Assert.Equal(BuildInfoSource.Env, result.Source);
                Assert.Null(result.Path);
            }
            finally
            {
                Directory.Delete(tempDir, true);
            }
        }

        [Fact]
        public void EnvBuildIdWithoutOtherVars()
        {
            var env = new Dictionary<string, string>
            {
                ["DEVLOGS_BUILD_ID"] = "direct-build-id"
            };

            var result = BuildInfoResolver.Resolve(new BuildInfoOptions
            {
                NowFn = FixedNow,
                GetEnvironmentVariable = CreateEnvGetter(env)
            });

            Assert.Equal("direct-build-id", result.BuildId);
            Assert.Null(result.Branch);
            Assert.Equal(FixedTimestamp, result.TimestampUtc);
            Assert.Equal(BuildInfoSource.Env, result.Source);
        }
    }

    public class EnvBranchAndTimestampTests
    {
        [Fact]
        public void EnvBranchGeneratesBuildId()
        {
            var env = new Dictionary<string, string>
            {
                ["DEVLOGS_BRANCH"] = "feature/my-feature"
            };

            var result = BuildInfoResolver.Resolve(new BuildInfoOptions
            {
                NowFn = FixedNow,
                GetEnvironmentVariable = CreateEnvGetter(env)
            });

            Assert.Equal($"feature/my-feature-{FixedTimestamp}", result.BuildId);
            Assert.Equal("feature/my-feature", result.Branch);
            Assert.Equal(FixedTimestamp, result.TimestampUtc);
            Assert.Equal(BuildInfoSource.Env, result.Source);
        }

        [Fact]
        public void EnvTimestampUsed()
        {
            var env = new Dictionary<string, string>
            {
                ["DEVLOGS_BRANCH"] = "main",
                ["DEVLOGS_BUILD_TIMESTAMP_UTC"] = "20250101T120000Z"
            };

            var result = BuildInfoResolver.Resolve(new BuildInfoOptions
            {
                NowFn = FixedNow,
                GetEnvironmentVariable = CreateEnvGetter(env)
            });

            Assert.Equal("main-20250101T120000Z", result.BuildId);
            Assert.Equal("20250101T120000Z", result.TimestampUtc);
            Assert.Equal(BuildInfoSource.Env, result.Source);
        }

        [Fact]
        public void CustomEnvPrefix()
        {
            var env = new Dictionary<string, string>
            {
                ["MYAPP_BUILD_ID"] = "custom-prefix-id"
            };

            var result = BuildInfoResolver.Resolve(new BuildInfoOptions
            {
                EnvPrefix = "MYAPP_",
                NowFn = FixedNow,
                GetEnvironmentVariable = CreateEnvGetter(env)
            });

            Assert.Equal("custom-prefix-id", result.BuildId);
            Assert.Equal(BuildInfoSource.Env, result.Source);
        }
    }

    public class FileProvidesInfoTests
    {
        [Fact]
        public void FileProvidesAllFields()
        {
            var tempDir = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
            Directory.CreateDirectory(tempDir);
            try
            {
                var buildFile = Path.Combine(tempDir, ".build.json");
                File.WriteAllText(buildFile, JsonSerializer.Serialize(new
                {
                    build_id = "file-build-123",
                    branch = "develop",
                    timestamp_utc = "20260115T093000Z"
                }));

                var result = BuildInfoResolver.Resolve(new BuildInfoOptions
                {
                    Path = buildFile,
                    NowFn = FixedNow,
                    GetEnvironmentVariable = CreateEnvGetter()
                });

                Assert.Equal("file-build-123", result.BuildId);
                Assert.Equal("develop", result.Branch);
                Assert.Equal("20260115T093000Z", result.TimestampUtc);
                Assert.Equal(BuildInfoSource.File, result.Source);
                Assert.Equal(buildFile, result.Path);
            }
            finally
            {
                Directory.Delete(tempDir, true);
            }
        }

        [Fact]
        public void FileWithExtraKeys()
        {
            var tempDir = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
            Directory.CreateDirectory(tempDir);
            try
            {
                var buildFile = Path.Combine(tempDir, ".build.json");
                File.WriteAllText(buildFile, JsonSerializer.Serialize(new
                {
                    build_id = "build-with-extras",
                    branch = "main",
                    timestamp_utc = "20260115T093000Z",
                    commit = "abc123",
                    pipeline_id = 12345
                }));

                var result = BuildInfoResolver.Resolve(new BuildInfoOptions
                {
                    Path = buildFile,
                    NowFn = FixedNow,
                    GetEnvironmentVariable = CreateEnvGetter()
                });

                Assert.Equal("build-with-extras", result.BuildId);
                Assert.Equal(BuildInfoSource.File, result.Source);
            }
            finally
            {
                Directory.Delete(tempDir, true);
            }
        }
    }

    public class EnvOverridesFileTests
    {
        [Fact]
        public void EnvBranchOverridesFileBranch()
        {
            var tempDir = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
            Directory.CreateDirectory(tempDir);
            try
            {
                var buildFile = Path.Combine(tempDir, ".build.json");
                File.WriteAllText(buildFile, JsonSerializer.Serialize(new
                {
                    build_id = "file-build-id",
                    branch = "file-branch",
                    timestamp_utc = "20260115T093000Z"
                }));

                var env = new Dictionary<string, string>
                {
                    ["DEVLOGS_BRANCH"] = "env-branch-override"
                };

                var result = BuildInfoResolver.Resolve(new BuildInfoOptions
                {
                    Path = buildFile,
                    NowFn = FixedNow,
                    GetEnvironmentVariable = CreateEnvGetter(env)
                });

                Assert.Equal("file-build-id", result.BuildId);
                Assert.Equal("env-branch-override", result.Branch);
                Assert.Equal(BuildInfoSource.File, result.Source);
            }
            finally
            {
                Directory.Delete(tempDir, true);
            }
        }
    }

    public class InvalidFileTests
    {
        [Fact]
        public void InvalidJsonFallsBackToGenerated()
        {
            var tempDir = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
            Directory.CreateDirectory(tempDir);
            try
            {
                var buildFile = Path.Combine(tempDir, ".build.json");
                File.WriteAllText(buildFile, "{ invalid json }");

                var result = BuildInfoResolver.Resolve(new BuildInfoOptions
                {
                    Path = buildFile,
                    NowFn = FixedNow,
                    GetEnvironmentVariable = CreateEnvGetter()
                });

                Assert.Equal($"unknown-{FixedTimestamp}", result.BuildId);
                Assert.Equal(BuildInfoSource.Generated, result.Source);
            }
            finally
            {
                Directory.Delete(tempDir, true);
            }
        }

        [Fact]
        public void FileMissingBuildIdFallsBack()
        {
            var tempDir = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
            Directory.CreateDirectory(tempDir);
            try
            {
                var buildFile = Path.Combine(tempDir, ".build.json");
                File.WriteAllText(buildFile, JsonSerializer.Serialize(new
                {
                    branch = "main",
                    timestamp_utc = "20260115T093000Z"
                    // No build_id!
                }));

                var result = BuildInfoResolver.Resolve(new BuildInfoOptions
                {
                    Path = buildFile,
                    NowFn = FixedNow,
                    GetEnvironmentVariable = CreateEnvGetter()
                });

                Assert.Equal($"unknown-{FixedTimestamp}", result.BuildId);
                Assert.Equal(BuildInfoSource.Generated, result.Source);
            }
            finally
            {
                Directory.Delete(tempDir, true);
            }
        }

        [Fact]
        public void NonexistentFileGenerates()
        {
            var tempDir = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
            var nonexistent = Path.Combine(tempDir, "does-not-exist.json");

            var result = BuildInfoResolver.Resolve(new BuildInfoOptions
            {
                Path = nonexistent,
                NowFn = FixedNow,
                GetEnvironmentVariable = CreateEnvGetter()
            });

            Assert.Equal($"unknown-{FixedTimestamp}", result.BuildId);
            Assert.Equal(BuildInfoSource.Generated, result.Source);
        }
    }

    public class WriteIfMissingTests
    {
        [Fact]
        public void WritesFileWhenMissing()
        {
            var tempDir = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
            Directory.CreateDirectory(tempDir);
            var originalDir = Directory.GetCurrentDirectory();
            try
            {
                Directory.SetCurrentDirectory(tempDir);

                var result = BuildInfoResolver.Resolve(new BuildInfoOptions
                {
                    WriteIfMissing = true,
                    NowFn = FixedNow,
                    GetEnvironmentVariable = CreateEnvGetter()
                });

                var expectedPath = Path.Combine(tempDir, ".build.json");
                Assert.True(File.Exists(expectedPath));
                Assert.Equal(expectedPath, result.Path);

                var content = File.ReadAllText(expectedPath);
                Assert.Contains($"unknown-{FixedTimestamp}", content);
            }
            finally
            {
                Directory.SetCurrentDirectory(originalDir);
                Directory.Delete(tempDir, true);
            }
        }

        [Fact]
        public void DoesNotOverwriteExistingFile()
        {
            var tempDir = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
            Directory.CreateDirectory(tempDir);
            try
            {
                var buildFile = Path.Combine(tempDir, ".build.json");
                var originalContent = JsonSerializer.Serialize(new
                {
                    build_id = "existing-build-id",
                    branch = "existing-branch",
                    timestamp_utc = "20250101T000000Z"
                });
                File.WriteAllText(buildFile, originalContent);

                var result = BuildInfoResolver.Resolve(new BuildInfoOptions
                {
                    Path = buildFile,
                    WriteIfMissing = true,
                    NowFn = FixedNow,
                    GetEnvironmentVariable = CreateEnvGetter()
                });

                Assert.Equal("existing-build-id", result.BuildId);
                Assert.Equal(BuildInfoSource.File, result.Source);

                // Verify file was not modified
                var newContent = File.ReadAllText(buildFile);
                Assert.Equal(originalContent, newContent);
            }
            finally
            {
                Directory.Delete(tempDir, true);
            }
        }
    }

    public class AllowGitTests
    {
        [Fact]
        public void AllowGitFalseDoesNotUseBranch()
        {
            var result = BuildInfoResolver.Resolve(new BuildInfoOptions
            {
                AllowGit = false,
                NowFn = FixedNow,
                GetEnvironmentVariable = CreateEnvGetter()
            });

            // Branch should be null since AllowGit=false and no env var
            Assert.Null(result.Branch);
            Assert.Equal(BuildInfoSource.Generated, result.Source);
        }
    }

    public class DeterministicBuildIdTests
    {
        [Fact]
        public void SameNowFnGivesSameResult()
        {
            var options = new BuildInfoOptions
            {
                NowFn = FixedNow,
                GetEnvironmentVariable = CreateEnvGetter()
            };

            var result1 = BuildInfoResolver.Resolve(options);
            var result2 = BuildInfoResolver.Resolve(options);

            Assert.Equal(result1.BuildId, result2.BuildId);
            Assert.Equal(result1.TimestampUtc, result2.TimestampUtc);
        }

        [Fact]
        public void DifferentNowFnGivesDifferentResult()
        {
            var otherDateTime = new DateTime(2025, 6, 15, 12, 0, 0, DateTimeKind.Utc);

            var result1 = BuildInfoResolver.Resolve(new BuildInfoOptions
            {
                NowFn = FixedNow,
                GetEnvironmentVariable = CreateEnvGetter()
            });

            var result2 = BuildInfoResolver.Resolve(new BuildInfoOptions
            {
                NowFn = () => otherDateTime,
                GetEnvironmentVariable = CreateEnvGetter()
            });

            Assert.NotEqual(result1.BuildId, result2.BuildId);
            Assert.Equal(FixedTimestamp, result1.TimestampUtc);
            Assert.Equal("20250615T120000Z", result2.TimestampUtc);
        }
    }

    public class SearchUpBehaviorTests
    {
        [Fact]
        public void FindsFileInParentDirectory()
        {
            var tempDir = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
            var parent = Path.Combine(tempDir, "project");
            var child = Path.Combine(parent, "src", "app");
            Directory.CreateDirectory(child);
            var originalDir = Directory.GetCurrentDirectory();
            try
            {
                var buildFile = Path.Combine(parent, ".build.json");
                File.WriteAllText(buildFile, JsonSerializer.Serialize(new
                {
                    build_id = "parent-build-id",
                    branch = "main",
                    timestamp_utc = "20260115T093000Z"
                }));

                Directory.SetCurrentDirectory(child);

                var result = BuildInfoResolver.Resolve(new BuildInfoOptions
                {
                    NowFn = FixedNow,
                    GetEnvironmentVariable = CreateEnvGetter()
                });

                Assert.Equal("parent-build-id", result.BuildId);
                Assert.Equal(BuildInfoSource.File, result.Source);
                Assert.Equal(buildFile, result.Path);
            }
            finally
            {
                Directory.SetCurrentDirectory(originalDir);
                Directory.Delete(tempDir, true);
            }
        }

        [Fact]
        public void StopsAtMaxDepth()
        {
            var tempDir = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
            Directory.CreateDirectory(tempDir);
            var originalDir = Directory.GetCurrentDirectory();
            try
            {
                // Create deeply nested structure
                var deep = tempDir;
                for (var i = 0; i < 15; i++)
                {
                    deep = Path.Combine(deep, "level");
                }
                Directory.CreateDirectory(deep);

                // Put build file at root
                var buildFile = Path.Combine(tempDir, ".build.json");
                File.WriteAllText(buildFile, JsonSerializer.Serialize(new
                {
                    build_id = "root-build-id",
                    branch = "main",
                    timestamp_utc = "20260115T093000Z"
                }));

                Directory.SetCurrentDirectory(deep);

                var result = BuildInfoResolver.Resolve(new BuildInfoOptions
                {
                    MaxSearchDepth = 3,
                    NowFn = FixedNow,
                    GetEnvironmentVariable = CreateEnvGetter()
                });

                Assert.Equal($"unknown-{FixedTimestamp}", result.BuildId);
                Assert.Equal(BuildInfoSource.Generated, result.Source);
            }
            finally
            {
                Directory.SetCurrentDirectory(originalDir);
                Directory.Delete(tempDir, true);
            }
        }

        [Fact]
        public void EnvBuildInfoPathOverride()
        {
            var tempDir = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
            var customDir = Path.Combine(tempDir, "custom", "location");
            Directory.CreateDirectory(customDir);
            var originalDir = Directory.GetCurrentDirectory();
            try
            {
                var customFile = Path.Combine(customDir, "my-build.json");
                File.WriteAllText(customFile, JsonSerializer.Serialize(new
                {
                    build_id = "custom-path-build-id",
                    branch = "custom",
                    timestamp_utc = "20260115T093000Z"
                }));

                var env = new Dictionary<string, string>
                {
                    ["DEVLOGS_BUILD_INFO_PATH"] = customFile
                };

                Directory.SetCurrentDirectory(tempDir);

                var result = BuildInfoResolver.Resolve(new BuildInfoOptions
                {
                    NowFn = FixedNow,
                    GetEnvironmentVariable = CreateEnvGetter(env)
                });

                Assert.Equal("custom-path-build-id", result.BuildId);
                Assert.Equal(BuildInfoSource.File, result.Source);
            }
            finally
            {
                Directory.SetCurrentDirectory(originalDir);
                Directory.Delete(tempDir, true);
            }
        }
    }

    public class ResolveBuildIdTests
    {
        [Fact]
        public void ReturnsStringOnly()
        {
            var result = BuildInfoResolver.ResolveBuildId(new BuildInfoOptions
            {
                NowFn = FixedNow,
                GetEnvironmentVariable = CreateEnvGetter()
            });

            Assert.Equal($"unknown-{FixedTimestamp}", result);
        }
    }

    public class GenerateBuildInfoFileTests
    {
        [Fact]
        public void GeneratesFileInCwd()
        {
            var tempDir = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
            Directory.CreateDirectory(tempDir);
            var originalDir = Directory.GetCurrentDirectory();
            try
            {
                Directory.SetCurrentDirectory(tempDir);

                var result = BuildInfoResolver.GenerateBuildInfoFile(
                    outputPath: null,
                    branch: null,
                    allowGit: false,
                    nowFn: FixedNow
                );

                var expectedPath = Path.Combine(tempDir, ".build.json");
                Assert.Equal(expectedPath, result);
                Assert.True(File.Exists(expectedPath));

                var content = File.ReadAllText(expectedPath);
                Assert.Contains($"unknown-{FixedTimestamp}", content);
            }
            finally
            {
                Directory.SetCurrentDirectory(originalDir);
                Directory.Delete(tempDir, true);
            }
        }

        [Fact]
        public void GeneratesAtCustomPath()
        {
            var tempDir = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
            Directory.CreateDirectory(tempDir);
            try
            {
                var customPath = Path.Combine(tempDir, "build", "info.json");

                var result = BuildInfoResolver.GenerateBuildInfoFile(
                    outputPath: customPath,
                    branch: null,
                    allowGit: false,
                    nowFn: FixedNow
                );

                Assert.Equal(customPath, result);
                Assert.True(File.Exists(customPath));
            }
            finally
            {
                Directory.Delete(tempDir, true);
            }
        }

        [Fact]
        public void ExplicitBranch()
        {
            var tempDir = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
            Directory.CreateDirectory(tempDir);
            try
            {
                var outputPath = Path.Combine(tempDir, ".build.json");

                var result = BuildInfoResolver.GenerateBuildInfoFile(
                    outputPath: outputPath,
                    branch: "release/v1.0",
                    allowGit: false,
                    nowFn: FixedNow
                );

                Assert.Equal(outputPath, result);

                var content = File.ReadAllText(outputPath);
                Assert.Contains("release/v1.0", content);
                Assert.Contains($"release/v1.0-{FixedTimestamp}", content);
            }
            finally
            {
                Directory.Delete(tempDir, true);
            }
        }
    }

    public class NullOptionsTests
    {
        [Fact]
        public void NullOptionsUsesDefaults()
        {
            // Clear any environment variables that might interfere
            var result = BuildInfoResolver.Resolve(new BuildInfoOptions
            {
                GetEnvironmentVariable = CreateEnvGetter()
            });

            Assert.NotNull(result);
            Assert.NotEmpty(result.BuildId);
            Assert.Equal(BuildInfoSource.Generated, result.Source);
        }
    }
}
