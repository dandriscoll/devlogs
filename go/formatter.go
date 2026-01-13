package devlogs

import (
	"bytes"
	"context"
	"log/slog"
	"os"
	"runtime"
	"strconv"
	"strings"
	"time"
)

// LogDocument represents the document structure sent to OpenSearch.
type LogDocument struct {
	DocType     string                 `json:"doc_type"`
	Timestamp   string                 `json:"timestamp"`
	Level       string                 `json:"level"`
	LevelNo     int                    `json:"levelno"`
	LoggerName  string                 `json:"logger_name"`
	Message     string                 `json:"message"`
	Pathname    *string                `json:"pathname"`
	LineNo      *int                   `json:"lineno"`
	FuncName    *string                `json:"funcName"`
	Area        *string                `json:"area"`
	OperationID *string                `json:"operation_id"`
	Thread      int                    `json:"thread"`
	Process     int                    `json:"process"`
	Exception   *string                `json:"exception,omitempty"`
	Features    map[string]interface{} `json:"features,omitempty"`
}

// FormatLogDocument converts an slog.Record to a LogDocument.
func FormatLogDocument(ctx context.Context, r slog.Record, loggerName string) *LogDocument {
	doc := &LogDocument{
		DocType:    "log_entry",
		Timestamp:  r.Time.UTC().Format("2006-01-02T15:04:05.000Z"),
		Level:      NormalizeLevel(r.Level),
		LevelNo:    LevelNumber(r.Level),
		LoggerName: loggerName,
		Message:    r.Message,
		Thread:     getGoroutineID(),
		Process:    os.Getpid(),
	}

	// Extract source info
	if r.PC != 0 {
		frames := runtime.CallersFrames([]uintptr{r.PC})
		frame, _ := frames.Next()
		if frame.File != "" {
			doc.Pathname = &frame.File
		}
		if frame.Line > 0 {
			doc.LineNo = &frame.Line
		}
		if frame.Function != "" {
			doc.FuncName = &frame.Function
		}
	}

	// Get context values
	if area := GetArea(ctx); area != "" {
		doc.Area = &area
	}
	if opID := GetOperationID(ctx); opID != "" {
		doc.OperationID = &opID
	}

	// Extract features from record attributes
	features := make(map[string]interface{})
	r.Attrs(func(a slog.Attr) bool {
		features[a.Key] = resolveValue(a.Value)
		return true
	})
	if len(features) > 0 {
		doc.Features = features
	}

	return doc
}

// resolveValue converts slog.Value to a JSON-serializable value.
func resolveValue(v slog.Value) interface{} {
	switch v.Kind() {
	case slog.KindString:
		return v.String()
	case slog.KindInt64:
		return v.Int64()
	case slog.KindUint64:
		return v.Uint64()
	case slog.KindFloat64:
		return v.Float64()
	case slog.KindBool:
		return v.Bool()
	case slog.KindDuration:
		return v.Duration().String()
	case slog.KindTime:
		return v.Time().Format(time.RFC3339)
	case slog.KindGroup:
		attrs := v.Group()
		m := make(map[string]interface{}, len(attrs))
		for _, a := range attrs {
			m[a.Key] = resolveValue(a.Value)
		}
		return m
	case slog.KindAny:
		return v.Any()
	default:
		return v.String()
	}
}

// getGoroutineID extracts the goroutine ID from runtime.Stack.
func getGoroutineID() int {
	var buf [64]byte
	n := runtime.Stack(buf[:], false)
	// Stack output starts with "goroutine <id> [...]"
	s := string(buf[:n])
	if strings.HasPrefix(s, "goroutine ") {
		s = s[len("goroutine "):]
		if idx := strings.IndexByte(s, ' '); idx > 0 {
			if id, err := strconv.Atoi(s[:idx]); err == nil {
				return id
			}
		}
	}
	return 0
}

// FormatException formats an error with stack trace for the exception field.
func FormatException(err error) string {
	if err == nil {
		return ""
	}

	var buf bytes.Buffer
	buf.WriteString(err.Error())
	buf.WriteString("\n\nStack trace:\n")

	// Get stack trace
	var stack [32]uintptr
	n := runtime.Callers(2, stack[:])
	frames := runtime.CallersFrames(stack[:n])

	for {
		frame, more := frames.Next()
		buf.WriteString("  ")
		buf.WriteString(frame.Function)
		buf.WriteString("\n    ")
		buf.WriteString(frame.File)
		buf.WriteString(":")
		buf.WriteString(strconv.Itoa(frame.Line))
		buf.WriteString("\n")
		if !more {
			break
		}
	}

	return buf.String()
}
