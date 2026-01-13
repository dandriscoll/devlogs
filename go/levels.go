package devlogs

import "log/slog"

// Python-compatible log level numbers.
const (
	LevelNoDebug    = 10
	LevelNoInfo     = 20
	LevelNoWarning  = 30
	LevelNoError    = 40
	LevelNoCritical = 50
)

// NormalizeLevel converts slog.Level to devlogs level string.
func NormalizeLevel(level slog.Level) string {
	switch {
	case level < slog.LevelInfo:
		return "debug"
	case level < slog.LevelWarn:
		return "info"
	case level < slog.LevelError:
		return "warning"
	default:
		return "error"
	}
}

// LevelNumber returns the Python-compatible level number.
func LevelNumber(level slog.Level) int {
	switch {
	case level < slog.LevelInfo:
		return LevelNoDebug
	case level < slog.LevelWarn:
		return LevelNoInfo
	case level < slog.LevelError:
		return LevelNoWarning
	default:
		return LevelNoError
	}
}
