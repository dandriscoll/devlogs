package devlogs

import (
	"context"
	"log/slog"
)

// Handler implements slog.Handler for devlogs (v2.0).
type Handler struct {
	client *Client
	cfg    *Config
	level  slog.Level
	attrs  []slog.Attr
	groups []string
	cb     *CircuitBreaker
}

// HandlerOption configures a Handler.
type HandlerOption func(*Handler)

// WithLevel sets the minimum log level.
func WithLevel(level slog.Level) HandlerOption {
	return func(h *Handler) {
		h.level = level
	}
}

// WithApplication sets the application name for v2.0 schema.
func WithApplication(name string) HandlerOption {
	return func(h *Handler) {
		h.cfg.Application = name
	}
}

// WithComponent sets the component name for v2.0 schema.
func WithComponent(name string) HandlerOption {
	return func(h *Handler) {
		h.cfg.Component = name
	}
}

// WithEnvironment sets the environment for v2.0 schema.
func WithEnvironment(env string) HandlerOption {
	return func(h *Handler) {
		h.cfg.Environment = env
	}
}

// WithVersion sets the version for v2.0 schema.
func WithVersion(version string) HandlerOption {
	return func(h *Handler) {
		h.cfg.Version = version
	}
}

// WithLoggerName sets the logger name (deprecated, use WithComponent).
func WithLoggerName(name string) HandlerOption {
	return WithComponent(name)
}

// NewHandler creates a new devlogs slog.Handler.
func NewHandler(cfg *Config, opts ...HandlerOption) (*Handler, error) {
	client := NewClient(cfg)
	return NewHandlerWithClient(client, cfg, opts...), nil
}

// NewHandlerWithClient creates a handler with a custom client.
func NewHandlerWithClient(client *Client, cfg *Config, opts ...HandlerOption) *Handler {
	h := &Handler{
		client: client,
		cfg:    cfg,
		level:  slog.LevelDebug,
		cb:     DefaultCircuitBreaker(),
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

	// Add handler-level attrs to record
	for _, a := range h.attrs {
		r.AddAttrs(a)
	}

	// Format document with v2.0 schema
	doc := FormatLogDocument(ctx, r, h.cfg)

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
