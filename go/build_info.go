package devlogs

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"time"
)

// BuildInfoSource indicates where the build info was obtained from.
type BuildInfoSource string

const (
	// SourceFile indicates build info was read from a file.
	SourceFile BuildInfoSource = "file"
	// SourceEnv indicates build info was provided via environment variables.
	SourceEnv BuildInfoSource = "env"
	// SourceGenerated indicates build info was generated at runtime.
	SourceGenerated BuildInfoSource = "generated"
)

// BuildInfo contains build information resolved from file, environment, or generated.
type BuildInfo struct {
	// BuildID is the unique build identifier (always non-empty).
	BuildID string `json:"build_id"`
	// Branch is the git branch name, if available.
	Branch string `json:"branch,omitempty"`
	// TimestampUTC is the UTC timestamp in format YYYYMMDDTHHMMSSZ.
	TimestampUTC string `json:"timestamp_utc"`
	// Source indicates where the build info was obtained from.
	Source BuildInfoSource `json:"-"`
	// Path is the file path used for build info, if any.
	Path string `json:"-"`
}

// BuildInfoOptions configures how build info is resolved.
type BuildInfoOptions struct {
	// Path is an explicit path to the build info file. If empty, searches upward from cwd.
	Path string
	// Filename is the filename to search for (default: ".build.json").
	Filename string
	// EnvPrefix is the environment variable prefix (default: "DEVLOGS_").
	EnvPrefix string
	// AllowGit enables git commands as fallback for branch detection (default: false).
	AllowGit bool
	// NowFn is a custom function to get current time (for testing). If nil, uses time.Now().
	NowFn func() time.Time
	// WriteIfMissing writes the build info file if not found (default: false).
	WriteIfMissing bool
	// MaxSearchDepth is the maximum parent directories to search (default: 10).
	MaxSearchDepth int
}

// DefaultBuildInfoOptions returns options with default values.
func DefaultBuildInfoOptions() *BuildInfoOptions {
	return &BuildInfoOptions{
		Filename:       ".build.json",
		EnvPrefix:      "DEVLOGS_",
		AllowGit:       false,
		WriteIfMissing: false,
		MaxSearchDepth: 10,
	}
}

// formatTimestamp formats a time as compact ISO-like UTC timestamp: YYYYMMDDTHHMMSSZ.
func formatTimestamp(t time.Time) string {
	return t.UTC().Format("20060102T150405Z")
}

// findBuildInfoFile searches for the build info file.
func findBuildInfoFile(opts *BuildInfoOptions) string {
	// Check env override first
	if envPath := os.Getenv(opts.EnvPrefix + "BUILD_INFO_PATH"); envPath != "" {
		if _, err := os.Stat(envPath); err == nil {
			return envPath
		}
		return ""
	}

	if opts.Path != "" {
		if _, err := os.Stat(opts.Path); err == nil {
			return opts.Path
		}
		return ""
	}

	// Search upward from cwd
	current, err := os.Getwd()
	if err != nil {
		return ""
	}

	for i := 0; i < opts.MaxSearchDepth; i++ {
		candidate := filepath.Join(current, opts.Filename)
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
		parent := filepath.Dir(current)
		if parent == current {
			// Reached filesystem root
			break
		}
		current = parent
	}

	return ""
}

// readBuildInfoFile reads and parses a build info JSON file.
func readBuildInfoFile(path string) (*BuildInfo, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	var info BuildInfo
	if err := json.Unmarshal(data, &info); err != nil {
		return nil, err
	}

	return &info, nil
}

// getGitBranch attempts to get the current git branch.
func getGitBranch() string {
	cmd := exec.Command("git", "rev-parse", "--abbrev-ref", "HEAD")
	output, err := cmd.Output()
	if err != nil {
		return ""
	}
	branch := string(output)
	// Trim whitespace
	for len(branch) > 0 && (branch[len(branch)-1] == '\n' || branch[len(branch)-1] == '\r') {
		branch = branch[:len(branch)-1]
	}
	if branch == "HEAD" {
		return "" // Detached HEAD state
	}
	return branch
}

// writeBuildInfoFile writes build info to a JSON file.
func writeBuildInfoFile(path string, info *BuildInfo) error {
	data, err := json.MarshalIndent(info, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')

	// Ensure parent directory exists
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return err
	}

	return os.WriteFile(path, data, 0644)
}

// ResolveBuildInfo resolves build information from file, environment, or generates it.
//
// Priority order:
//  1. Environment variable BUILD_ID (if set) takes highest precedence
//  2. Build info file (if found and valid)
//  3. Environment variables for branch/timestamp
//  4. Git (if AllowGit=true)
//  5. Generated values
//
// Never returns an error - always returns valid BuildInfo with at least a generated build_id.
func ResolveBuildInfo(opts *BuildInfoOptions) *BuildInfo {
	if opts == nil {
		opts = DefaultBuildInfoOptions()
	}

	// Apply defaults for empty values
	if opts.Filename == "" {
		opts.Filename = ".build.json"
	}
	if opts.EnvPrefix == "" {
		opts.EnvPrefix = "DEVLOGS_"
	}
	if opts.MaxSearchDepth == 0 {
		opts.MaxSearchDepth = 10
	}

	nowFn := opts.NowFn
	if nowFn == nil {
		nowFn = time.Now
	}

	// Environment variable names
	envBuildID := opts.EnvPrefix + "BUILD_ID"
	envBranch := opts.EnvPrefix + "BRANCH"
	envTimestamp := opts.EnvPrefix + "BUILD_TIMESTAMP_UTC"

	// Check for direct BUILD_ID env override (highest precedence)
	if directBuildID := os.Getenv(envBuildID); directBuildID != "" {
		branch := os.Getenv(envBranch)
		timestamp := os.Getenv(envTimestamp)
		if timestamp == "" {
			timestamp = formatTimestamp(nowFn())
		}
		return &BuildInfo{
			BuildID:      directBuildID,
			Branch:       branch,
			TimestampUTC: timestamp,
			Source:       SourceEnv,
			Path:         "",
		}
	}

	// Try to find and read build info file
	filePath := findBuildInfoFile(opts)
	var fileData *BuildInfo
	if filePath != "" {
		fileData, _ = readBuildInfoFile(filePath)
	}

	if fileData != nil && fileData.BuildID != "" {
		// File found and valid - use its data
		// Allow env overrides for individual fields
		branch := os.Getenv(envBranch)
		if branch == "" {
			branch = fileData.Branch
		}
		timestamp := os.Getenv(envTimestamp)
		if timestamp == "" {
			timestamp = fileData.TimestampUTC
		}
		if timestamp == "" {
			timestamp = formatTimestamp(nowFn())
		}

		return &BuildInfo{
			BuildID:      fileData.BuildID,
			Branch:       branch,
			TimestampUTC: timestamp,
			Source:       SourceFile,
			Path:         filePath,
		}
	}

	// Check if env provides branch and/or timestamp
	envBranchValue := os.Getenv(envBranch)
	envTimestampValue := os.Getenv(envTimestamp)

	// Determine branch
	var branch string
	if envBranchValue != "" {
		branch = envBranchValue
	} else if opts.AllowGit {
		branch = getGitBranch()
	}

	// Determine timestamp
	var timestamp string
	if envTimestampValue != "" {
		timestamp = envTimestampValue
	} else {
		timestamp = formatTimestamp(nowFn())
	}

	// Generate build_id
	branchForID := branch
	if branchForID == "" {
		branchForID = "unknown"
	}
	buildID := branchForID + "-" + timestamp

	// Determine source
	source := SourceGenerated
	if envBranchValue != "" || envTimestampValue != "" {
		source = SourceEnv
	}

	result := &BuildInfo{
		BuildID:      buildID,
		Branch:       branch,
		TimestampUTC: timestamp,
		Source:       source,
		Path:         filePath,
	}

	// Optionally write to file
	if opts.WriteIfMissing && fileData == nil {
		writePath := filePath
		if writePath == "" {
			cwd, err := os.Getwd()
			if err == nil {
				writePath = filepath.Join(cwd, opts.Filename)
			}
		}
		if writePath != "" {
			// Best effort - ignore errors
			_ = writeBuildInfoFile(writePath, result)
			result.Path = writePath
		}
	}

	return result
}

// ResolveBuildID is a convenience function that returns only the build_id string.
func ResolveBuildID(opts *BuildInfoOptions) string {
	return ResolveBuildInfo(opts).BuildID
}

// GenerateBuildInfoFile generates a .build.json file for use at runtime.
// This is a utility for CI/CD pipelines to generate the build info file during build.
//
// Returns the path to the written file, or empty string if write failed.
func GenerateBuildInfoFile(outputPath string, branch string, allowGit bool, nowFn func() time.Time) string {
	if nowFn == nil {
		nowFn = time.Now
	}

	if outputPath == "" {
		cwd, err := os.Getwd()
		if err != nil {
			return ""
		}
		outputPath = filepath.Join(cwd, ".build.json")
	}

	// Determine branch
	if branch == "" && allowGit {
		branch = getGitBranch()
	}

	timestamp := formatTimestamp(nowFn())
	branchForID := branch
	if branchForID == "" {
		branchForID = "unknown"
	}
	buildID := branchForID + "-" + timestamp

	info := &BuildInfo{
		BuildID:      buildID,
		Branch:       branch,
		TimestampUTC: timestamp,
		Source:       SourceGenerated,
		Path:         outputPath,
	}

	if err := writeBuildInfoFile(outputPath, info); err != nil {
		return ""
	}

	return outputPath
}
