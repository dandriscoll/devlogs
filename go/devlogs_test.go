package devlogs

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

// --- Config Tests ---

func TestDefaultConfig(t *testing.T) {
	cfg := DefaultConfig()

	if cfg.Host != "localhost" {
		t.Errorf("expected Host=localhost, got %s", cfg.Host)
	}
	if cfg.Port != 9200 {
		t.Errorf("expected Port=9200, got %d", cfg.Port)
	}
	if cfg.User != "admin" {
		t.Errorf("expected User=admin, got %s", cfg.User)
	}
	if cfg.Password != "admin" {
		t.Errorf("expected Password=admin, got %s", cfg.Password)
	}
	if cfg.Index != "devlogs-0001" {
		t.Errorf("expected Index=devlogs-0001, got %s", cfg.Index)
	}
	if cfg.Timeout != 30*time.Second {
		t.Errorf("expected Timeout=30s, got %v", cfg.Timeout)
	}
}

func TestLoadConfigFromEnvironment(t *testing.T) {
	// Set environment variables
	os.Setenv("DEVLOGS_OPENSEARCH_HOST", "testhost")
	os.Setenv("DEVLOGS_OPENSEARCH_PORT", "9999")
	os.Setenv("DEVLOGS_OPENSEARCH_USER", "testuser")
	os.Setenv("DEVLOGS_OPENSEARCH_PASS", "testpass")
	os.Setenv("DEVLOGS_INDEX", "test-index")
	defer func() {
		os.Unsetenv("DEVLOGS_OPENSEARCH_HOST")
		os.Unsetenv("DEVLOGS_OPENSEARCH_PORT")
		os.Unsetenv("DEVLOGS_OPENSEARCH_USER")
		os.Unsetenv("DEVLOGS_OPENSEARCH_PASS")
		os.Unsetenv("DEVLOGS_INDEX")
	}()

	cfg, err := LoadConfig()
	if err != nil {
		t.Fatalf("LoadConfig failed: %v", err)
	}

	if cfg.Host != "testhost" {
		t.Errorf("expected Host=testhost, got %s", cfg.Host)
	}
	if cfg.Port != 9999 {
		t.Errorf("expected Port=9999, got %d", cfg.Port)
	}
	if cfg.User != "testuser" {
		t.Errorf("expected User=testuser, got %s", cfg.User)
	}
	if cfg.Password != "testpass" {
		t.Errorf("expected Password=testpass, got %s", cfg.Password)
	}
	if cfg.Index != "test-index" {
		t.Errorf("expected Index=test-index, got %s", cfg.Index)
	}
}

func TestLoadConfigFromURL(t *testing.T) {
	os.Setenv("DEVLOGS_OPENSEARCH_URL", "http://urluser:urlpass@urlhost:8888/urlindex")
	defer os.Unsetenv("DEVLOGS_OPENSEARCH_URL")

	cfg, err := LoadConfig()
	if err != nil {
		t.Fatalf("LoadConfig failed: %v", err)
	}

	if cfg.Host != "urlhost" {
		t.Errorf("expected Host=urlhost, got %s", cfg.Host)
	}
	if cfg.Port != 8888 {
		t.Errorf("expected Port=8888, got %d", cfg.Port)
	}
	if cfg.User != "urluser" {
		t.Errorf("expected User=urluser, got %s", cfg.User)
	}
	if cfg.Password != "urlpass" {
		t.Errorf("expected Password=urlpass, got %s", cfg.Password)
	}
	if cfg.Index != "urlindex" {
		t.Errorf("expected Index=urlindex, got %s", cfg.Index)
	}
}

// --- Level Tests ---

func TestNormalizeLevel(t *testing.T) {
	tests := []struct {
		level    slog.Level
		expected string
	}{
		{slog.LevelDebug, "debug"},
		{slog.LevelInfo, "info"},
		{slog.LevelWarn, "warning"},
		{slog.LevelError, "error"},
	}

	for _, tc := range tests {
		result := NormalizeLevel(tc.level)
		if result != tc.expected {
			t.Errorf("NormalizeLevel(%v) = %s, expected %s", tc.level, result, tc.expected)
		}
	}
}

func TestLevelNumber(t *testing.T) {
	tests := []struct {
		level    slog.Level
		expected int
	}{
		{slog.LevelDebug, 10},
		{slog.LevelInfo, 20},
		{slog.LevelWarn, 30},
		{slog.LevelError, 40},
	}

	for _, tc := range tests {
		result := LevelNumber(tc.level)
		if result != tc.expected {
			t.Errorf("LevelNumber(%v) = %d, expected %d", tc.level, result, tc.expected)
		}
	}
}

// --- Context Tests ---

func TestWithOperation(t *testing.T) {
	ctx := WithOperation(context.Background(), "op-123", "web")

	if opID := GetOperationID(ctx); opID != "op-123" {
		t.Errorf("expected operation_id=op-123, got %s", opID)
	}
	if area := GetArea(ctx); area != "web" {
		t.Errorf("expected area=web, got %s", area)
	}
}

func TestWithOperationGeneratesUUID(t *testing.T) {
	ctx := WithOperation(context.Background(), "", "")

	opID := GetOperationID(ctx)
	if opID == "" {
		t.Error("expected generated UUID, got empty string")
	}
	// UUID format check
	if len(opID) != 36 {
		t.Errorf("expected UUID length 36, got %d", len(opID))
	}
}

func TestSetAreaGlobal(t *testing.T) {
	SetArea("global-area")
	defer SetArea("")

	ctx := context.Background()
	if area := GetArea(ctx); area != "global-area" {
		t.Errorf("expected area=global-area, got %s", area)
	}
}

func TestContextAreaOverridesGlobal(t *testing.T) {
	SetArea("global")
	defer SetArea("")

	ctx := WithArea(context.Background(), "local")
	if area := GetArea(ctx); area != "local" {
		t.Errorf("expected area=local, got %s", area)
	}
}

// --- Circuit Breaker Tests ---

func TestCircuitBreakerStartsClosed(t *testing.T) {
	cb := NewCircuitBreaker(60*time.Second, 10*time.Second)
	if cb.IsOpen() {
		t.Error("expected circuit breaker to start closed")
	}
}

func TestCircuitBreakerOpensOnFailure(t *testing.T) {
	cb := NewCircuitBreaker(60*time.Second, 10*time.Second)
	cb.RecordFailure(NewConnectionError("test error", nil))

	if !cb.IsOpen() {
		t.Error("expected circuit breaker to be open after failure")
	}
}

func TestCircuitBreakerClosesOnSuccess(t *testing.T) {
	cb := NewCircuitBreaker(60*time.Second, 10*time.Second)
	cb.RecordFailure(NewConnectionError("test error", nil))
	cb.RecordSuccess()

	if cb.IsOpen() {
		t.Error("expected circuit breaker to be closed after success")
	}
}

func TestCircuitBreakerAutoResets(t *testing.T) {
	cb := NewCircuitBreaker(50*time.Millisecond, 10*time.Millisecond)
	cb.RecordFailure(NewConnectionError("test error", nil))

	if !cb.IsOpen() {
		t.Error("expected circuit breaker to be open")
	}

	// Wait for duration to expire
	time.Sleep(100 * time.Millisecond)

	if cb.IsOpen() {
		t.Error("expected circuit breaker to auto-reset after duration")
	}
}

// --- Error Tests ---

func TestErrorTypes(t *testing.T) {
	tests := []struct {
		name string
		err  error
	}{
		{"ConnectionError", NewConnectionError("test", nil)},
		{"AuthError", NewAuthError("test")},
		{"IndexNotFoundError", NewIndexNotFoundError("test-index")},
		{"QueryError", NewQueryError("test")},
	}

	for _, tc := range tests {
		if tc.err.Error() == "" {
			t.Errorf("%s.Error() returned empty string", tc.name)
		}
	}
}

func TestConnectionErrorUnwrap(t *testing.T) {
	cause := NewAuthError("cause")
	err := NewConnectionError("wrapper", cause)

	if unwrapped := err.Unwrap(); unwrapped != cause {
		t.Errorf("Unwrap() did not return cause")
	}
}

// --- Formatter Tests ---

func TestFormatLogDocument(t *testing.T) {
	SetArea("test-area")
	defer SetArea("")

	ctx := WithOperation(context.Background(), "test-op-id", "")
	r := slog.NewRecord(time.Now(), slog.LevelInfo, "test message", 0)
	r.AddAttrs(slog.String("key", "value"))

	doc := FormatLogDocument(ctx, r, "test-logger")

	if doc.DocType != "log_entry" {
		t.Errorf("expected doc_type=log_entry, got %s", doc.DocType)
	}
	if doc.Level != "info" {
		t.Errorf("expected level=info, got %s", doc.Level)
	}
	if doc.LevelNo != 20 {
		t.Errorf("expected levelno=20, got %d", doc.LevelNo)
	}
	if doc.LoggerName != "test-logger" {
		t.Errorf("expected logger_name=test-logger, got %s", doc.LoggerName)
	}
	if doc.Message != "test message" {
		t.Errorf("expected message='test message', got %s", doc.Message)
	}
	if doc.OperationID == nil || *doc.OperationID != "test-op-id" {
		t.Errorf("expected operation_id=test-op-id, got %v", doc.OperationID)
	}
	if doc.Area == nil || *doc.Area != "test-area" {
		t.Errorf("expected area=test-area, got %v", doc.Area)
	}
	if doc.Features["key"] != "value" {
		t.Errorf("expected features.key=value, got %v", doc.Features["key"])
	}
}

func TestFormatLogDocumentTimestamp(t *testing.T) {
	ctx := context.Background()
	now := time.Now()
	r := slog.NewRecord(now, slog.LevelInfo, "test", 0)

	doc := FormatLogDocument(ctx, r, "test")

	if !strings.HasSuffix(doc.Timestamp, "Z") {
		t.Errorf("expected timestamp to end with Z, got %s", doc.Timestamp)
	}
}

// --- Client Tests ---

func TestClientIndex(t *testing.T) {
	var receivedDoc map[string]interface{}

	// Create mock server
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST, got %s", r.Method)
		}
		if !strings.HasSuffix(r.URL.Path, "/_doc") {
			t.Errorf("expected path to end with /_doc, got %s", r.URL.Path)
		}
		if r.Header.Get("Authorization") == "" {
			t.Error("expected Authorization header")
		}
		if r.Header.Get("Content-Type") != "application/json" {
			t.Errorf("expected Content-Type=application/json, got %s", r.Header.Get("Content-Type"))
		}

		json.NewDecoder(r.Body).Decode(&receivedDoc)
		w.WriteHeader(http.StatusCreated)
	}))
	defer server.Close()

	// Parse server URL
	cfg := DefaultConfig()
	cfg.Host = strings.TrimPrefix(server.URL, "http://")
	cfg.Host = strings.Split(cfg.Host, ":")[0]
	portStr := strings.Split(server.URL, ":")[2]
	var port int
	for _, c := range portStr {
		if c >= '0' && c <= '9' {
			port = port*10 + int(c-'0')
		} else {
			break
		}
	}
	cfg.Port = port

	client := NewClient(cfg)

	doc := &LogDocument{
		DocType:    "log_entry",
		Message:    "test",
		Level:      "info",
		LoggerName: "test",
	}

	err := client.Index(context.Background(), doc)
	if err != nil {
		t.Fatalf("Index failed: %v", err)
	}

	if receivedDoc["doc_type"] != "log_entry" {
		t.Errorf("expected doc_type=log_entry, got %v", receivedDoc["doc_type"])
	}
}

func TestClientHandles401(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
	}))
	defer server.Close()

	cfg := DefaultConfig()
	cfg.Host = strings.TrimPrefix(server.URL, "http://")
	cfg.Host = strings.Split(cfg.Host, ":")[0]
	portStr := strings.Split(server.URL, ":")[2]
	var port int
	for _, c := range portStr {
		if c >= '0' && c <= '9' {
			port = port*10 + int(c-'0')
		} else {
			break
		}
	}
	cfg.Port = port

	client := NewClient(cfg)
	err := client.Index(context.Background(), map[string]string{"test": "data"})

	if _, ok := err.(*AuthError); !ok {
		t.Errorf("expected AuthError, got %T", err)
	}
}

func TestClientHandles404(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	cfg := DefaultConfig()
	cfg.Host = strings.TrimPrefix(server.URL, "http://")
	cfg.Host = strings.Split(cfg.Host, ":")[0]
	portStr := strings.Split(server.URL, ":")[2]
	var port int
	for _, c := range portStr {
		if c >= '0' && c <= '9' {
			port = port*10 + int(c-'0')
		} else {
			break
		}
	}
	cfg.Port = port

	client := NewClient(cfg)
	err := client.Index(context.Background(), map[string]string{"test": "data"})

	if _, ok := err.(*IndexNotFoundError); !ok {
		t.Errorf("expected IndexNotFoundError, got %T", err)
	}
}

// --- Handler Tests ---

func TestHandlerEnabled(t *testing.T) {
	cfg := DefaultConfig()
	handler, _ := NewHandler(cfg, WithLevel(slog.LevelInfo))

	if handler.Enabled(context.Background(), slog.LevelDebug) {
		t.Error("expected Debug to be disabled when level is Info")
	}
	if !handler.Enabled(context.Background(), slog.LevelInfo) {
		t.Error("expected Info to be enabled when level is Info")
	}
	if !handler.Enabled(context.Background(), slog.LevelError) {
		t.Error("expected Error to be enabled when level is Info")
	}
}

func TestHandlerWithAttrs(t *testing.T) {
	cfg := DefaultConfig()
	handler, _ := NewHandler(cfg)

	newHandler := handler.WithAttrs([]slog.Attr{slog.String("key", "value")})

	h := newHandler.(*Handler)
	if len(h.attrs) != 1 {
		t.Errorf("expected 1 attr, got %d", len(h.attrs))
	}
}

func TestHandlerWithGroup(t *testing.T) {
	cfg := DefaultConfig()
	handler, _ := NewHandler(cfg)

	newHandler := handler.WithGroup("mygroup")

	h := newHandler.(*Handler)
	if len(h.groups) != 1 || h.groups[0] != "mygroup" {
		t.Errorf("expected groups=[mygroup], got %v", h.groups)
	}
}
