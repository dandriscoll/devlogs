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
	if cfg.Application != "unknown" {
		t.Errorf("expected Application=unknown, got %s", cfg.Application)
	}
	if cfg.Component != "go" {
		t.Errorf("expected Component=go, got %s", cfg.Component)
	}
}

func TestLoadConfigFromEnvironment(t *testing.T) {
	// Set environment variables
	os.Setenv("DEVLOGS_OPENSEARCH_HOST", "testhost")
	os.Setenv("DEVLOGS_OPENSEARCH_PORT", "9999")
	os.Setenv("DEVLOGS_OPENSEARCH_USER", "testuser")
	os.Setenv("DEVLOGS_OPENSEARCH_PASS", "testpass")
	os.Setenv("DEVLOGS_INDEX", "test-index")
	os.Setenv("DEVLOGS_APPLICATION", "test-app")
	os.Setenv("DEVLOGS_COMPONENT", "test-component")
	defer func() {
		os.Unsetenv("DEVLOGS_OPENSEARCH_HOST")
		os.Unsetenv("DEVLOGS_OPENSEARCH_PORT")
		os.Unsetenv("DEVLOGS_OPENSEARCH_USER")
		os.Unsetenv("DEVLOGS_OPENSEARCH_PASS")
		os.Unsetenv("DEVLOGS_INDEX")
		os.Unsetenv("DEVLOGS_APPLICATION")
		os.Unsetenv("DEVLOGS_COMPONENT")
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
	if cfg.Application != "test-app" {
		t.Errorf("expected Application=test-app, got %s", cfg.Application)
	}
	if cfg.Component != "test-component" {
		t.Errorf("expected Component=test-component, got %s", cfg.Component)
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

// --- Formatter Tests (v2.0 schema) ---

func TestFormatLogDocument(t *testing.T) {
	SetArea("test-area")
	defer SetArea("")

	ctx := WithOperation(context.Background(), "test-op-id", "")
	r := slog.NewRecord(time.Now(), slog.LevelInfo, "test message", 0)
	r.AddAttrs(slog.String("key", "value"))

	cfg := DefaultConfig()
	cfg.Application = "test-app"
	cfg.Component = "test-component"

	doc := FormatLogDocument(ctx, r, cfg)

	if doc.DocType != "log_entry" {
		t.Errorf("expected doc_type=log_entry, got %s", doc.DocType)
	}
	if doc.Application != "test-app" {
		t.Errorf("expected application=test-app, got %s", doc.Application)
	}
	if doc.Component != "test-component" {
		t.Errorf("expected component=test-component, got %s", doc.Component)
	}
	if doc.Level != "info" {
		t.Errorf("expected level=info, got %s", doc.Level)
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
	if doc.Fields["key"] != "value" {
		t.Errorf("expected fields.key=value, got %v", doc.Fields["key"])
	}
	// Check source struct
	if doc.Source.Logger != "test-component" {
		t.Errorf("expected source.logger=test-component, got %s", doc.Source.Logger)
	}
	// Check process struct
	if doc.Process.ID == 0 {
		t.Error("expected process.id to be non-zero")
	}
}

func TestFormatLogDocumentTimestamp(t *testing.T) {
	ctx := context.Background()
	now := time.Now()
	r := slog.NewRecord(now, slog.LevelInfo, "test", 0)

	cfg := DefaultConfig()
	doc := FormatLogDocument(ctx, r, cfg)

	if !strings.HasSuffix(doc.Timestamp, "Z") {
		t.Errorf("expected timestamp to end with Z, got %s", doc.Timestamp)
	}
}

func TestFormatLogDocumentWithOptionalFields(t *testing.T) {
	ctx := context.Background()
	r := slog.NewRecord(time.Now(), slog.LevelInfo, "test", 0)

	cfg := DefaultConfig()
	cfg.Environment = "production"
	cfg.Version = "1.2.3"

	doc := FormatLogDocument(ctx, r, cfg)

	if doc.Environment == nil || *doc.Environment != "production" {
		t.Errorf("expected environment=production, got %v", doc.Environment)
	}
	if doc.Version == nil || *doc.Version != "1.2.3" {
		t.Errorf("expected version=1.2.3, got %v", doc.Version)
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
		DocType:     "log_entry",
		Application: "test-app",
		Component:   "test",
		Timestamp:   time.Now().UTC().Format("2006-01-02T15:04:05.000Z"),
		Message:     "test",
		Level:       "info",
		Source: LogSource{
			Logger: "test",
		},
		Process: LogProcess{
			ID:     1,
			Thread: 1,
		},
	}

	err := client.Index(context.Background(), doc)
	if err != nil {
		t.Fatalf("Index failed: %v", err)
	}

	if receivedDoc["doc_type"] != "log_entry" {
		t.Errorf("expected doc_type=log_entry, got %v", receivedDoc["doc_type"])
	}
	if receivedDoc["application"] != "test-app" {
		t.Errorf("expected application=test-app, got %v", receivedDoc["application"])
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

func TestHandlerWithApplication(t *testing.T) {
	cfg := DefaultConfig()
	handler, _ := NewHandler(cfg, WithApplication("custom-app"))

	if handler.cfg.Application != "custom-app" {
		t.Errorf("expected Application=custom-app, got %s", handler.cfg.Application)
	}
}

func TestHandlerWithComponent(t *testing.T) {
	cfg := DefaultConfig()
	handler, _ := NewHandler(cfg, WithComponent("custom-component"))

	if handler.cfg.Component != "custom-component" {
		t.Errorf("expected Component=custom-component, got %s", handler.cfg.Component)
	}
}
