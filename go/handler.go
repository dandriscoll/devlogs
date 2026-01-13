package devlogs

import (
	"context"
	"log/slog"
)

// Handler implements slog.Handler for devlogs.
type Handler struct {
	client     *Client
	level      slog.Level
	loggerName string
	attrs      []slog.Attr
	groups     []string
	cb         *CircuitBreaker
}

// HandlerOption configures a Handler.
type HandlerOption func(*Handler)

// WithLevel sets the minimum log level.
func WithLevel(level slog.Level) HandlerOption {
	return func(h *Handler) {
		h.level = level
	}
}

// WithLoggerName sets the logger name included in documents.
func WithLoggerName(name string) HandlerOption {
	return func(h *Handler) {
		h.loggerName = name
	}
}

// NewHandler creates a new devlogs slog.Handler.
func NewHandler(cfg *Config, opts ...HandlerOption) (*Handler, error) {
	client := NewClient(cfg)
	return NewHandlerWithClient(client, cfg, opts...), nil
}

// NewHandlerWithClient creates a handler with a custom client.
func NewHandlerWithClient(client *Client, cfg *Config, opts ...HandlerOption) *Handler {
	h := &Handler{
		client:     client,
		level:      slog.LevelDebug,
		loggerName: "go",
		cb:         DefaultCircuitBreaker(),
	}

	for _, opt := range opts {
		opt(h)
	}

	return h
}

// Enabled reports whether the handler handles records at the given level.
func (h *Handler) Enabled(_ context.Context, level slog.Level) bool {
	return level >= h.level
}

// Handle handles a log record.
func (h *Handler) Handle(ctx context.Context, r slog.Record) error {
	// Check circuit breaker
	if h.cb.IsOpen() {
		return nil
	}

	// Build logger name with groups
	loggerName := h.loggerName
	for _, g := range h.groups {
		loggerName += "." + g
	}

	// Add handler-level attrs to record
	for _, a := range h.attrs {
		r.AddAttrs(a)
	}

	// Format document
	doc := FormatLogDocument(ctx, r, loggerName)

	// Fire-and-forget indexing
	go func() {
		err := h.client.Index(context.Background(), doc)
		if err != nil {
			h.cb.RecordFailure(err)
		} else {
			h.cb.RecordSuccess()
		}
	}()

	return nil
}

// WithAttrs returns a new Handler with additional attributes.
func (h *Handler) WithAttrs(attrs []slog.Attr) slog.Handler {
	newHandler := *h
	newHandler.attrs = make([]slog.Attr, len(h.attrs)+len(attrs))
	copy(newHandler.attrs, h.attrs)
	copy(newHandler.attrs[len(h.attrs):], attrs)
	return &newHandler
}

// WithGroup returns a new Handler with a group name.
func (h *Handler) WithGroup(name string) slog.Handler {
	if name == "" {
		return h
	}
	newHandler := *h
	newHandler.groups = make([]string, len(h.groups)+1)
	copy(newHandler.groups, h.groups)
	newHandler.groups[len(h.groups)] = name
	return &newHandler
}
