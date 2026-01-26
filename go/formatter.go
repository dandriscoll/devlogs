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

// LogSource contains source location info (v2.0 schema).
type LogSource struct {
	Logger   string  `json:"logger"`
	Pathname *string `json:"pathname"`
	LineNo   *int    `json:"lineno"`
	FuncName *string `json:"funcName"`
}

// LogProcess contains process/thread info (v2.0 schema).
type LogProcess struct {
	ID     int `json:"id"`
	Thread int `json:"thread"`
}

// LogDocument represents the document structure sent to OpenSearch (v2.0 schema).
type LogDocument struct {
	DocType string `json:"doc_type"`

	// Required fields
	Application string `json:"application"`
	Component   string `json:"component"`
	Timestamp   string `json:"timestamp"`

	// Top-level log fields
	Message string  `json:"message"`
	Level   string  `json:"level"`
	Area    *string `json:"area"`

	// Optional metadata
	Environment *string `json:"environment,omitempty"`
	Version     *string `json:"version,omitempty"`
	OperationID *string `json:"operation_id"`

	// Custom fields (renamed from features)
	Fields map[string]interface{} `json:"fields,omitempty"`

	// Source and process info
	Source    LogSource  `json:"source"`
	Process   LogProcess `json:"process"`
	Exception *string    `json:"exception,omitempty"`
}

// FormatLogDocument converts an slog.Record to a LogDocument using v2.0 schema.
func FormatLogDocument(ctx context.Context, r slog.Record, cfg *Config) *LogDocument {
	doc := &LogDocument{
		DocType:     "log_entry",
		Application: cfg.Application,
		Component:   cfg.Component,
		Timestamp:   r.Time.UTC().Format("2006-01-02T15:04:05.000Z"),
		Message:     r.Message,
		Level:       NormalizeLevel(r.Level),
		Source: LogSource{
			Logger: cfg.Component, // Use component as default logger name
		},
		Process: LogProcess{
			ID:     os.Getpid(),
			Thread: getGoroutineID(),
		},
	}

	// Optional metadata
	if cfg.Environment != "" {
		doc.Environment = &cfg.Environment
	}
	if cfg.Version != "" {
		doc.Version = &cfg.Version
	}

	// Extract source info
	if r.PC != 0 {
		frames := runtime.CallersFrames([]uintptr{r.PC})
		frame, _ := frames.Next()
		if frame.File != "" {
			doc.Source.Pathname = &frame.File
		}
		if frame.Line > 0 {
			doc.Source.LineNo = &frame.Line
		}
		if frame.Function != "" {
			doc.Source.FuncName = &frame.Function
			// Use function name as logger if available
			doc.Source.Logger = frame.Function
		}
	}

	// Get context values
	if area := GetArea(ctx); area != "" {
		doc.Area = &area
	}
	if opID := GetOperationID(ctx); opID != "" {
		doc.OperationID = &opID
	}

	// Extract fields from record attributes (renamed from features)
	fields := make(map[string]interface{})
	r.Attrs(func(a slog.Attr) bool {
		fields[a.Key] = resolveValue(a.Value)
		return true
	})
	if len(fields) > 0 {
		doc.Fields = fields
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
