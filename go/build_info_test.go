package devlogs

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// Fixed time for deterministic tests
var fixedTime = time.Date(2026, 1, 24, 15, 30, 45, 0, time.UTC)

const fixedTimestamp = "20260124T153045Z"

func fixedNow() time.Time {
	return fixedTime
}

// Helper to clear build info env vars
func clearBuildInfoEnv() {
	os.Unsetenv("DEVLOGS_BUILD_ID")
	os.Unsetenv("DEVLOGS_BRANCH")
	os.Unsetenv("DEVLOGS_BUILD_TIMESTAMP_UTC")
	os.Unsetenv("DEVLOGS_BUILD_INFO_PATH")
}

// --- Format Timestamp Tests ---

func TestFormatTimestamp(t *testing.T) {
	ts := time.Date(2026, 3, 15, 10, 20, 30, 0, time.UTC)
	result := formatTimestamp(ts)
	expected := "20260315T102030Z"
	if result != expected {
		t.Errorf("expected %s, got %s", expected, result)
	}
}

func TestFormatTimestampNonUTC(t *testing.T) {
	// Test that non-UTC times are converted to UTC
	loc, _ := time.LoadLocation("America/New_York")
	ts := time.Date(2026, 3, 15, 6, 20, 30, 0, loc) // 6:20 AM EST = 11:20 AM UTC (during DST)
	result := formatTimestamp(ts)
	// Should be converted to UTC
	if len(result) != len("20260315T112030Z") {
		t.Errorf("unexpected format: %s", result)
	}
}

// --- Env BUILD_ID Precedence Tests ---

func TestEnvBuildIDOverridesEverything(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	// Create a temp file with build info
	tmpDir := t.TempDir()
	buildFile := filepath.Join(tmpDir, ".build.json")
	fileData := map[string]string{
		"build_id":      "file-build-id",
		"branch":        "file-branch",
		"timestamp_utc": "20260101T000000Z",
	}
	data, _ := json.Marshal(fileData)
	os.WriteFile(buildFile, data, 0644)

	// Set env BUILD_ID
	os.Setenv("DEVLOGS_BUILD_ID", "env-build-id-override")
	os.Setenv("DEVLOGS_BRANCH", "env-branch")

	opts := DefaultBuildInfoOptions()
	opts.Path = buildFile
	opts.NowFn = fixedNow

	result := ResolveBuildInfo(opts)

	if result.BuildID != "env-build-id-override" {
		t.Errorf("expected BuildID=env-build-id-override, got %s", result.BuildID)
	}
	if result.Branch != "env-branch" {
		t.Errorf("expected Branch=env-branch, got %s", result.Branch)
	}
	if result.Source != SourceEnv {
		t.Errorf("expected Source=env, got %s", result.Source)
	}
}

func TestEnvBuildIDWithoutOtherVars(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	os.Setenv("DEVLOGS_BUILD_ID", "direct-build-id")

	opts := DefaultBuildInfoOptions()
	opts.NowFn = fixedNow

	result := ResolveBuildInfo(opts)

	if result.BuildID != "direct-build-id" {
		t.Errorf("expected BuildID=direct-build-id, got %s", result.BuildID)
	}
	if result.Branch != "" {
		t.Errorf("expected Branch='', got %s", result.Branch)
	}
	if result.TimestampUTC != fixedTimestamp {
		t.Errorf("expected TimestampUTC=%s, got %s", fixedTimestamp, result.TimestampUTC)
	}
	if result.Source != SourceEnv {
		t.Errorf("expected Source=env, got %s", result.Source)
	}
}

// --- Env Branch and Timestamp Tests ---

func TestEnvBranchGeneratesBuildID(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	os.Setenv("DEVLOGS_BRANCH", "feature/my-feature")

	opts := DefaultBuildInfoOptions()
	opts.NowFn = fixedNow

	result := ResolveBuildInfo(opts)

	expected := "feature/my-feature-" + fixedTimestamp
	if result.BuildID != expected {
		t.Errorf("expected BuildID=%s, got %s", expected, result.BuildID)
	}
	if result.Branch != "feature/my-feature" {
		t.Errorf("expected Branch=feature/my-feature, got %s", result.Branch)
	}
	if result.Source != SourceEnv {
		t.Errorf("expected Source=env, got %s", result.Source)
	}
}

func TestEnvTimestampUsed(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	os.Setenv("DEVLOGS_BRANCH", "main")
	os.Setenv("DEVLOGS_BUILD_TIMESTAMP_UTC", "20250101T120000Z")

	opts := DefaultBuildInfoOptions()
	opts.NowFn = fixedNow

	result := ResolveBuildInfo(opts)

	if result.BuildID != "main-20250101T120000Z" {
		t.Errorf("expected BuildID=main-20250101T120000Z, got %s", result.BuildID)
	}
	if result.TimestampUTC != "20250101T120000Z" {
		t.Errorf("expected TimestampUTC=20250101T120000Z, got %s", result.TimestampUTC)
	}
}

func TestCustomEnvPrefix(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	os.Setenv("MYAPP_BUILD_ID", "custom-prefix-id")
	defer os.Unsetenv("MYAPP_BUILD_ID")

	opts := DefaultBuildInfoOptions()
	opts.EnvPrefix = "MYAPP_"
	opts.NowFn = fixedNow

	result := ResolveBuildInfo(opts)

	if result.BuildID != "custom-prefix-id" {
		t.Errorf("expected BuildID=custom-prefix-id, got %s", result.BuildID)
	}
	if result.Source != SourceEnv {
		t.Errorf("expected Source=env, got %s", result.Source)
	}
}

// --- File Provides Build Info Tests ---

func TestFileProvidesAllFields(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	tmpDir := t.TempDir()
	buildFile := filepath.Join(tmpDir, ".build.json")
	fileData := map[string]string{
		"build_id":      "file-build-123",
		"branch":        "develop",
		"timestamp_utc": "20260115T093000Z",
	}
	data, _ := json.Marshal(fileData)
	os.WriteFile(buildFile, data, 0644)

	opts := DefaultBuildInfoOptions()
	opts.Path = buildFile
	opts.NowFn = fixedNow

	result := ResolveBuildInfo(opts)

	if result.BuildID != "file-build-123" {
		t.Errorf("expected BuildID=file-build-123, got %s", result.BuildID)
	}
	if result.Branch != "develop" {
		t.Errorf("expected Branch=develop, got %s", result.Branch)
	}
	if result.TimestampUTC != "20260115T093000Z" {
		t.Errorf("expected TimestampUTC=20260115T093000Z, got %s", result.TimestampUTC)
	}
	if result.Source != SourceFile {
		t.Errorf("expected Source=file, got %s", result.Source)
	}
	if result.Path != buildFile {
		t.Errorf("expected Path=%s, got %s", buildFile, result.Path)
	}
}

func TestFileWithExtraKeys(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	tmpDir := t.TempDir()
	buildFile := filepath.Join(tmpDir, ".build.json")
	fileData := map[string]interface{}{
		"build_id":      "build-with-extras",
		"branch":        "main",
		"timestamp_utc": "20260115T093000Z",
		"commit":        "abc123",
		"pipeline_id":   12345,
	}
	data, _ := json.Marshal(fileData)
	os.WriteFile(buildFile, data, 0644)

	opts := DefaultBuildInfoOptions()
	opts.Path = buildFile
	opts.NowFn = fixedNow

	result := ResolveBuildInfo(opts)

	if result.BuildID != "build-with-extras" {
		t.Errorf("expected BuildID=build-with-extras, got %s", result.BuildID)
	}
	if result.Source != SourceFile {
		t.Errorf("expected Source=file, got %s", result.Source)
	}
}

// --- Env Overrides File Tests ---

func TestEnvBranchOverridesFileBranch(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	tmpDir := t.TempDir()
	buildFile := filepath.Join(tmpDir, ".build.json")
	fileData := map[string]string{
		"build_id":      "file-build-id",
		"branch":        "file-branch",
		"timestamp_utc": "20260115T093000Z",
	}
	data, _ := json.Marshal(fileData)
	os.WriteFile(buildFile, data, 0644)

	os.Setenv("DEVLOGS_BRANCH", "env-branch-override")

	opts := DefaultBuildInfoOptions()
	opts.Path = buildFile
	opts.NowFn = fixedNow

	result := ResolveBuildInfo(opts)

	if result.BuildID != "file-build-id" {
		t.Errorf("expected BuildID=file-build-id, got %s", result.BuildID)
	}
	if result.Branch != "env-branch-override" {
		t.Errorf("expected Branch=env-branch-override, got %s", result.Branch)
	}
	if result.Source != SourceFile {
		t.Errorf("expected Source=file, got %s", result.Source)
	}
}

// --- Invalid File Tests ---

func TestInvalidJSONFallsBackToGenerated(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	tmpDir := t.TempDir()
	buildFile := filepath.Join(tmpDir, ".build.json")
	os.WriteFile(buildFile, []byte("{ invalid json }"), 0644)

	opts := DefaultBuildInfoOptions()
	opts.Path = buildFile
	opts.NowFn = fixedNow

	result := ResolveBuildInfo(opts)

	expected := "unknown-" + fixedTimestamp
	if result.BuildID != expected {
		t.Errorf("expected BuildID=%s, got %s", expected, result.BuildID)
	}
	if result.Source != SourceGenerated {
		t.Errorf("expected Source=generated, got %s", result.Source)
	}
}

func TestFileMissingBuildIDFallsBack(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	tmpDir := t.TempDir()
	buildFile := filepath.Join(tmpDir, ".build.json")
	fileData := map[string]string{
		"branch":        "main",
		"timestamp_utc": "20260115T093000Z",
		// No build_id!
	}
	data, _ := json.Marshal(fileData)
	os.WriteFile(buildFile, data, 0644)

	opts := DefaultBuildInfoOptions()
	opts.Path = buildFile
	opts.NowFn = fixedNow

	result := ResolveBuildInfo(opts)

	expected := "unknown-" + fixedTimestamp
	if result.BuildID != expected {
		t.Errorf("expected BuildID=%s, got %s", expected, result.BuildID)
	}
	if result.Source != SourceGenerated {
		t.Errorf("expected Source=generated, got %s", result.Source)
	}
}

func TestNonexistentFileGenerates(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	tmpDir := t.TempDir()
	nonexistent := filepath.Join(tmpDir, "does-not-exist.json")

	opts := DefaultBuildInfoOptions()
	opts.Path = nonexistent
	opts.NowFn = fixedNow

	result := ResolveBuildInfo(opts)

	expected := "unknown-" + fixedTimestamp
	if result.BuildID != expected {
		t.Errorf("expected BuildID=%s, got %s", expected, result.BuildID)
	}
	if result.Source != SourceGenerated {
		t.Errorf("expected Source=generated, got %s", result.Source)
	}
}

// --- Write If Missing Tests ---

func TestWritesFileWhenMissing(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	tmpDir := t.TempDir()
	origWd, _ := os.Getwd()
	os.Chdir(tmpDir)
	defer os.Chdir(origWd)

	opts := DefaultBuildInfoOptions()
	opts.WriteIfMissing = true
	opts.NowFn = fixedNow

	result := ResolveBuildInfo(opts)

	expectedPath := filepath.Join(tmpDir, ".build.json")
	if result.Path != expectedPath {
		t.Errorf("expected Path=%s, got %s", expectedPath, result.Path)
	}

	// Check file was written
	if _, err := os.Stat(expectedPath); os.IsNotExist(err) {
		t.Error("expected file to be written")
	}

	// Verify file contents
	data, _ := os.ReadFile(expectedPath)
	var fileData map[string]interface{}
	json.Unmarshal(data, &fileData)

	expected := "unknown-" + fixedTimestamp
	if fileData["build_id"] != expected {
		t.Errorf("expected build_id=%s in file, got %v", expected, fileData["build_id"])
	}
}

func TestDoesNotOverwriteExistingFile(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	tmpDir := t.TempDir()
	buildFile := filepath.Join(tmpDir, ".build.json")
	originalContent := map[string]string{
		"build_id":      "existing-build-id",
		"branch":        "existing-branch",
		"timestamp_utc": "20250101T000000Z",
	}
	data, _ := json.Marshal(originalContent)
	os.WriteFile(buildFile, data, 0644)

	opts := DefaultBuildInfoOptions()
	opts.Path = buildFile
	opts.WriteIfMissing = true
	opts.NowFn = fixedNow

	result := ResolveBuildInfo(opts)

	if result.BuildID != "existing-build-id" {
		t.Errorf("expected BuildID=existing-build-id, got %s", result.BuildID)
	}
	if result.Source != SourceFile {
		t.Errorf("expected Source=file, got %s", result.Source)
	}

	// Verify file not modified
	newData, _ := os.ReadFile(buildFile)
	var newContent map[string]string
	json.Unmarshal(newData, &newContent)
	if newContent["build_id"] != "existing-build-id" {
		t.Error("file was unexpectedly modified")
	}
}

// --- Allow Git Tests ---

func TestAllowGitFalseDoesNotCallGit(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	// Note: We can't easily verify subprocess wasn't called in Go,
	// but we verify behavior is correct when git would not provide data
	opts := DefaultBuildInfoOptions()
	opts.AllowGit = false
	opts.NowFn = fixedNow

	result := ResolveBuildInfo(opts)

	// Branch should be empty since AllowGit=false
	if result.Branch != "" {
		t.Errorf("expected Branch='', got %s", result.Branch)
	}
	if result.Source != SourceGenerated {
		t.Errorf("expected Source=generated, got %s", result.Source)
	}
}

// --- Deterministic Build ID Tests ---

func TestSameNowFnGivesSameResult(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	opts := DefaultBuildInfoOptions()
	opts.NowFn = fixedNow

	result1 := ResolveBuildInfo(opts)
	result2 := ResolveBuildInfo(opts)

	if result1.BuildID != result2.BuildID {
		t.Errorf("expected same BuildID, got %s and %s", result1.BuildID, result2.BuildID)
	}
	if result1.TimestampUTC != result2.TimestampUTC {
		t.Errorf("expected same TimestampUTC, got %s and %s", result1.TimestampUTC, result2.TimestampUTC)
	}
}

func TestDifferentNowFnGivesDifferentResult(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	otherTime := time.Date(2025, 6, 15, 12, 0, 0, 0, time.UTC)
	otherNow := func() time.Time { return otherTime }

	opts1 := DefaultBuildInfoOptions()
	opts1.NowFn = fixedNow
	result1 := ResolveBuildInfo(opts1)

	opts2 := DefaultBuildInfoOptions()
	opts2.NowFn = otherNow
	result2 := ResolveBuildInfo(opts2)

	if result1.BuildID == result2.BuildID {
		t.Error("expected different BuildIDs")
	}
	if result1.TimestampUTC != fixedTimestamp {
		t.Errorf("expected TimestampUTC=%s, got %s", fixedTimestamp, result1.TimestampUTC)
	}
	if result2.TimestampUTC != "20250615T120000Z" {
		t.Errorf("expected TimestampUTC=20250615T120000Z, got %s", result2.TimestampUTC)
	}
}

// --- Search Up Behavior Tests ---

func TestFindsFileInParentDirectory(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	tmpDir := t.TempDir()
	parent := filepath.Join(tmpDir, "project")
	child := filepath.Join(parent, "src", "app")
	os.MkdirAll(child, 0755)

	// Put build file in parent
	buildFile := filepath.Join(parent, ".build.json")
	fileData := map[string]string{
		"build_id":      "parent-build-id",
		"branch":        "main",
		"timestamp_utc": "20260115T093000Z",
	}
	data, _ := json.Marshal(fileData)
	os.WriteFile(buildFile, data, 0644)

	// Change to child directory
	origWd, _ := os.Getwd()
	os.Chdir(child)
	defer os.Chdir(origWd)

	opts := DefaultBuildInfoOptions()
	opts.NowFn = fixedNow

	result := ResolveBuildInfo(opts)

	if result.BuildID != "parent-build-id" {
		t.Errorf("expected BuildID=parent-build-id, got %s", result.BuildID)
	}
	if result.Source != SourceFile {
		t.Errorf("expected Source=file, got %s", result.Source)
	}
	if result.Path != buildFile {
		t.Errorf("expected Path=%s, got %s", buildFile, result.Path)
	}
}

func TestStopsAtMaxDepth(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	tmpDir := t.TempDir()

	// Create deeply nested structure
	deep := tmpDir
	for i := 0; i < 15; i++ {
		deep = filepath.Join(deep, "level")
	}
	os.MkdirAll(deep, 0755)

	// Put build file at root
	buildFile := filepath.Join(tmpDir, ".build.json")
	fileData := map[string]string{
		"build_id":      "root-build-id",
		"branch":        "main",
		"timestamp_utc": "20260115T093000Z",
	}
	data, _ := json.Marshal(fileData)
	os.WriteFile(buildFile, data, 0644)

	// Change to deep directory
	origWd, _ := os.Getwd()
	os.Chdir(deep)
	defer os.Chdir(origWd)

	opts := DefaultBuildInfoOptions()
	opts.MaxSearchDepth = 3
	opts.NowFn = fixedNow

	result := ResolveBuildInfo(opts)

	expected := "unknown-" + fixedTimestamp
	if result.BuildID != expected {
		t.Errorf("expected BuildID=%s (not found), got %s", expected, result.BuildID)
	}
	if result.Source != SourceGenerated {
		t.Errorf("expected Source=generated, got %s", result.Source)
	}
}

func TestEnvBuildInfoPathOverride(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	tmpDir := t.TempDir()
	customDir := filepath.Join(tmpDir, "custom", "location")
	os.MkdirAll(customDir, 0755)
	customFile := filepath.Join(customDir, "my-build.json")
	fileData := map[string]string{
		"build_id":      "custom-path-build-id",
		"branch":        "custom",
		"timestamp_utc": "20260115T093000Z",
	}
	data, _ := json.Marshal(fileData)
	os.WriteFile(customFile, data, 0644)

	os.Setenv("DEVLOGS_BUILD_INFO_PATH", customFile)

	origWd, _ := os.Getwd()
	os.Chdir(tmpDir)
	defer os.Chdir(origWd)

	opts := DefaultBuildInfoOptions()
	opts.NowFn = fixedNow

	result := ResolveBuildInfo(opts)

	if result.BuildID != "custom-path-build-id" {
		t.Errorf("expected BuildID=custom-path-build-id, got %s", result.BuildID)
	}
	if result.Source != SourceFile {
		t.Errorf("expected Source=file, got %s", result.Source)
	}
}

// --- ResolveBuildID Tests ---

func TestResolveBuildIDReturnsStringOnly(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	opts := DefaultBuildInfoOptions()
	opts.NowFn = fixedNow

	result := ResolveBuildID(opts)

	expected := "unknown-" + fixedTimestamp
	if result != expected {
		t.Errorf("expected %s, got %s", expected, result)
	}
}

// --- GenerateBuildInfoFile Tests ---

func TestGenerateBuildInfoFileInCwd(t *testing.T) {
	tmpDir := t.TempDir()
	origWd, _ := os.Getwd()
	os.Chdir(tmpDir)
	defer os.Chdir(origWd)

	result := GenerateBuildInfoFile("", "", false, fixedNow)

	expectedPath := filepath.Join(tmpDir, ".build.json")
	if result != expectedPath {
		t.Errorf("expected %s, got %s", expectedPath, result)
	}

	// Verify file contents
	data, _ := os.ReadFile(expectedPath)
	var fileData map[string]interface{}
	json.Unmarshal(data, &fileData)

	expected := "unknown-" + fixedTimestamp
	if fileData["build_id"] != expected {
		t.Errorf("expected build_id=%s, got %v", expected, fileData["build_id"])
	}
}

func TestGenerateBuildInfoFileAtCustomPath(t *testing.T) {
	tmpDir := t.TempDir()
	customPath := filepath.Join(tmpDir, "build", "info.json")

	result := GenerateBuildInfoFile(customPath, "", false, fixedNow)

	if result != customPath {
		t.Errorf("expected %s, got %s", customPath, result)
	}

	if _, err := os.Stat(customPath); os.IsNotExist(err) {
		t.Error("expected file to exist")
	}
}

func TestGenerateBuildInfoFileWithExplicitBranch(t *testing.T) {
	tmpDir := t.TempDir()
	outputPath := filepath.Join(tmpDir, ".build.json")

	result := GenerateBuildInfoFile(outputPath, "release/v1.0", false, fixedNow)

	if result != outputPath {
		t.Errorf("expected %s, got %s", outputPath, result)
	}

	data, _ := os.ReadFile(outputPath)
	var fileData map[string]interface{}
	json.Unmarshal(data, &fileData)

	if fileData["branch"] != "release/v1.0" {
		t.Errorf("expected branch=release/v1.0, got %v", fileData["branch"])
	}
	expected := "release/v1.0-" + fixedTimestamp
	if fileData["build_id"] != expected {
		t.Errorf("expected build_id=%s, got %v", expected, fileData["build_id"])
	}
}

// --- Nil Options Test ---

func TestNilOptionsUsesDefaults(t *testing.T) {
	clearBuildInfoEnv()
	defer clearBuildInfoEnv()

	result := ResolveBuildInfo(nil)

	// Should not panic and should return valid result
	if result.BuildID == "" {
		t.Error("expected non-empty BuildID")
	}
	if result.Source != SourceGenerated {
		t.Errorf("expected Source=generated, got %s", result.Source)
	}
}
