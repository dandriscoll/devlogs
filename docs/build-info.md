# Build Info Helper

The build info helper provides a stable build identifier that applications can use to tag every log entry without requiring git at runtime.

Available for: **Python**, **Go**, **TypeScript/Browser**, **.NET**

## Quick Start

### Python

```python
from devlogs.build_info import resolve_build_info

# Resolve build info (from file, env, or generate)
bi = resolve_build_info(write_if_missing=True)

# Use with devlogs logger
from devlogs.handler import OpenSearchHandler
import logging

handler = OpenSearchHandler(level=logging.INFO)
logging.getLogger().addHandler(handler)

# Add build info as extra fields
logging.info("Application started", extra={
    "features": {
        "build_id": bi.build_id,
        "branch": bi.branch,
    }
})
```

### Go

```go
import "github.com/dandriscoll/devlogs/go"

// Resolve build info
opts := devlogs.DefaultBuildInfoOptions()
opts.WriteIfMissing = true
bi := devlogs.ResolveBuildInfo(opts)

// Use with logger
log.Printf("build_id=%s branch=%s", bi.BuildID, bi.Branch)
```

### TypeScript/Browser

```typescript
import { resolveBuildInfo } from 'devlogs-browser';

// With build-time injected data
import buildData from './.build.json';
const bi = resolveBuildInfo({ data: buildData });

console.log(`build_id=${bi.buildId} branch=${bi.branch}`);
```

### .NET

```csharp
using Devlogs.BuildInfo;

// Resolve build info
var bi = BuildInfoResolver.Resolve(new BuildInfoOptions
{
    WriteIfMissing = true
});

logger.LogInformation("Started with build {BuildId}", bi.BuildId);
```

## Why No Git at Runtime?

Devlogs is designed to be lightweight in production. Requiring git at runtime creates problems:

1. **Containerized environments** often don't include git to minimize image size
2. **CI artifacts** deployed to production don't have `.git` directories
3. **Subprocess calls** add latency and can fail unpredictably
4. **Permission issues** in sandboxed/restricted environments

Instead, build information should be captured during the build/CI phase and read at runtime.

## API Reference

### `resolve_build_info(...) -> BuildInfo`

Resolves build information with the following priority:

1. `DEVLOGS_BUILD_ID` env var (highest precedence)
2. Build info file (`.build.json`)
3. Other env vars (`DEVLOGS_BRANCH`, `DEVLOGS_BUILD_TIMESTAMP_UTC`)
4. Git commands (only if `allow_git=True`)
5. Generated values (fallback)

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | `str \| Path \| None` | `None` | Explicit path to build info file |
| `filename` | `str` | `".build.json"` | Filename to search for |
| `env_prefix` | `str` | `"DEVLOGS_"` | Environment variable prefix |
| `allow_git` | `bool` | `False` | Allow git commands as fallback |
| `now_fn` | `Callable[[], datetime]` | `datetime.now(UTC)` | Custom datetime function (for testing) |
| `write_if_missing` | `bool` | `False` | Write file if not found |
| `max_search_depth` | `int` | `10` | Max parent directories to search |

**Returns:** `BuildInfo` dataclass with:

| Field | Type | Description |
|-------|------|-------------|
| `build_id` | `str` | Unique identifier (always non-empty) |
| `branch` | `str \| None` | Branch name if available |
| `timestamp_utc` | `str` | UTC timestamp (`YYYYMMDDTHHMMSSZ`) |
| `source` | `str` | One of: `"file"`, `"env"`, `"generated"` |
| `path` | `str \| None` | File path used, if any |

### `resolve_build_id(...) -> str`

Convenience wrapper returning only the `build_id` string. Accepts the same parameters as `resolve_build_info()`.

### `generate_build_info_file(...) -> Path | None`

Utility for CI/CD pipelines to generate the build info file during build.

```python
from devlogs.build_info import generate_build_info_file

# Generate with git branch detection
generate_build_info_file("dist/.build.json", allow_git=True)

# Or with explicit branch
generate_build_info_file("dist/.build.json", branch="release/v1.2.3")
```

## Build Info File Format

The `.build.json` file uses a simple JSON format:

```json
{
  "build_id": "main-20260124T153045Z",
  "branch": "main",
  "timestamp_utc": "20260124T153045Z"
}
```

Extra keys are allowed and ignored:

```json
{
  "build_id": "main-20260124T153045Z",
  "branch": "main",
  "timestamp_utc": "20260124T153045Z",
  "commit": "abc1234",
  "pipeline_id": "12345",
  "build_number": 42
}
```

## Generated Build ID Format

When build info is generated (not from file/env), the format is:

```
{branch}-{timestamp}
```

Examples:
- `main-20260124T153045Z`
- `feature/auth-20260124T153045Z`
- `unknown-20260124T153045Z` (when branch cannot be determined)

## File Search Behavior

When `path` is not provided, the module searches for the build info file:

1. Check `DEVLOGS_BUILD_INFO_PATH` env var for explicit path
2. Search upward from current working directory
3. Stop after `max_search_depth` parent directories (default: 10)

This allows placing `.build.json` in the project root while running from subdirectories.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DEVLOGS_BUILD_ID` | Direct build ID override (highest precedence) |
| `DEVLOGS_BRANCH` | Branch name |
| `DEVLOGS_BUILD_TIMESTAMP_UTC` | Timestamp in `YYYYMMDDTHHMMSSZ` format |
| `DEVLOGS_BUILD_INFO_PATH` | Explicit path to build info file |

Custom prefix example (using `MYAPP_` instead of `DEVLOGS_`):

```python
bi = resolve_build_info(env_prefix="MYAPP_")
# Looks for: MYAPP_BUILD_ID, MYAPP_BRANCH, etc.
```

## CI/CD Integration

### GitHub Actions

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Generate build info
        run: |
          cat > .build.json << EOF
          {
            "build_id": "${{ github.ref_name }}-$(date -u +%Y%m%dT%H%M%SZ)",
            "branch": "${{ github.ref_name }}",
            "timestamp_utc": "$(date -u +%Y%m%dT%H%M%SZ)",
            "commit": "${{ github.sha }}",
            "run_id": "${{ github.run_id }}"
          }
          EOF

      - name: Build application
        run: make build

      # .build.json is included in build artifacts
```

### Jenkins (Declarative Pipeline)

```groovy
pipeline {
    agent any
    stages {
        stage('Generate Build Info') {
            steps {
                script {
                    def timestamp = new Date().format("yyyyMMdd'T'HHmmss'Z'", TimeZone.getTimeZone('UTC'))
                    def branch = env.BRANCH_NAME ?: 'unknown'
                    def buildId = "${branch}-${timestamp}"

                    writeFile file: '.build.json', text: """{
                        "build_id": "${buildId}",
                        "branch": "${branch}",
                        "timestamp_utc": "${timestamp}",
                        "build_number": ${env.BUILD_NUMBER}
                    }"""
                }
            }
        }
        stage('Build') {
            steps {
                sh 'make build'
            }
        }
    }
}
```

### Using Python in CI

```bash
# In your CI script
python -c "
from devlogs.build_info import generate_build_info_file
generate_build_info_file('dist/.build.json', allow_git=True)
"
```

## Recommended Log Fields

When using devlogs, consider including these fields for effective log analysis:

| Field | Description | Example |
|-------|-------------|---------|
| `app` | Application name | `"myapp"` |
| `env` | Environment | `"production"`, `"staging"`, `"dev"` |
| `component` | Component/service | `"api"`, `"worker"`, `"web"` |
| `pipeline_stage` | CI/CD stage | `"build"`, `"test"`, `"deploy"` |
| `build_id` | Build identifier | `"main-20260124T153045Z"` |
| `branch` | Git branch | `"main"`, `"feature/auth"` |

Example integration:

```python
import os
import logging
from devlogs.build_info import resolve_build_info
from devlogs.handler import OpenSearchHandler

# Resolve build info at startup
bi = resolve_build_info(write_if_missing=True)

# Create handler with extra fields
handler = OpenSearchHandler(level=logging.INFO)
logging.getLogger().addHandler(handler)

# Create a logging adapter to include build info in all logs
class BuildInfoAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.get('extra', {})
        features = extra.get('features', {})
        features.update({
            'app': 'myapp',
            'env': os.getenv('ENVIRONMENT', 'dev'),
            'build_id': self.extra['build_id'],
            'branch': self.extra['branch'],
        })
        extra['features'] = features
        kwargs['extra'] = extra
        return msg, kwargs

logger = BuildInfoAdapter(
    logging.getLogger(__name__),
    {'build_id': bi.build_id, 'branch': bi.branch}
)

logger.info("Application started")
```

## Where to Put the Build Info File

**During development:**
- Project root (`.build.json`)
- The search-up behavior finds it from any subdirectory

**During CI/build:**
- Generate in build output directory (`dist/.build.json`, `build/.build.json`)
- Include in deployment artifacts

**At runtime:**
- Working directory or a parent directory
- Or set `DEVLOGS_BUILD_INFO_PATH` to an absolute path
- Or use environment variables directly

## Error Handling

The module is designed to never fail logging:

- Invalid JSON files are silently ignored
- Missing files fall back to generated values
- Git failures (when `allow_git=True`) are silently ignored
- Write failures (when `write_if_missing=True`) don't raise exceptions

This ensures your application always has a valid `build_id`, even in edge cases.

## Language-Specific API

### Go API

```go
// Types
type BuildInfo struct {
    BuildID      string          // Always non-empty
    Branch       string          // May be empty
    TimestampUTC string          // Format: YYYYMMDDTHHMMSSZ
    Source       BuildInfoSource // SourceFile, SourceEnv, or SourceGenerated
    Path         string          // File path used, if any
}

type BuildInfoOptions struct {
    Path           string              // Explicit file path
    Filename       string              // Default: ".build.json"
    EnvPrefix      string              // Default: "DEVLOGS_"
    AllowGit       bool                // Default: false
    NowFn          func() time.Time    // For testing
    WriteIfMissing bool                // Default: false
    MaxSearchDepth int                 // Default: 10
}

// Functions
func ResolveBuildInfo(opts *BuildInfoOptions) *BuildInfo
func ResolveBuildID(opts *BuildInfoOptions) string
func GenerateBuildInfoFile(outputPath, branch string, allowGit bool, nowFn func() time.Time) string
```

### TypeScript API

```typescript
interface BuildInfo {
  buildId: string;        // Always non-empty
  branch: string | null;
  timestampUtc: string;   // Format: YYYYMMDDTHHMMSSZ
  source: 'file' | 'env' | 'generated';
  path: string | null;
}

interface BuildInfoOptions {
  data?: BuildInfoFile;                    // Injected build data
  envPrefix?: string;                      // Default: "DEVLOGS_"
  nowFn?: () => Date;                      // For testing
  env?: Record<string, string | undefined>; // Custom env vars
}

// Functions
function resolveBuildInfo(options?: BuildInfoOptions): BuildInfo
function resolveBuildId(options?: BuildInfoOptions): string
function createBuildInfoData(options?: { branch?: string; nowFn?: () => Date }): BuildInfoFile
```

### .NET API

```csharp
// Types
public sealed class BuildInfo
{
    public string BuildId { get; init; }        // Always non-empty
    public string? Branch { get; init; }
    public string TimestampUtc { get; init; }   // Format: YYYYMMDDTHHMMSSZ
    public BuildInfoSource Source { get; init; } // File, Env, or Generated
    public string? Path { get; init; }
}

public sealed class BuildInfoOptions
{
    public string? Path { get; set; }
    public string Filename { get; set; } = ".build.json";
    public string EnvPrefix { get; set; } = "DEVLOGS_";
    public bool AllowGit { get; set; }
    public Func<DateTime>? NowFn { get; set; }
    public bool WriteIfMissing { get; set; }
    public int MaxSearchDepth { get; set; } = 10;
}

// Static methods
public static class BuildInfoResolver
{
    public static BuildInfo Resolve(BuildInfoOptions? options = null);
    public static string ResolveBuildId(BuildInfoOptions? options = null);
    public static string? GenerateBuildInfoFile(
        string? outputPath = null,
        string? branch = null,
        bool allowGit = true,
        Func<DateTime>? nowFn = null);
}
