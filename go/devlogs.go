// Package devlogs provides a logging handler that sends logs to OpenSearch.
//
// It integrates with Go's log/slog package and provides operation correlation,
// circuit breaker protection, and automatic context propagation.
//
// Basic usage:
//
//	cfg, err := devlogs.LoadConfig()
//	if err != nil {
//	    log.Fatal(err)
//	}
//
//	handler, err := devlogs.NewHandler(cfg)
//	if err != nil {
//	    log.Fatal(err)
//	}
//
//	slog.SetDefault(slog.New(handler))
//	slog.Info("Application started")
//
// With operation context:
//
//	ctx := devlogs.WithOperation(context.Background(), "req-123", "api")
//	slog.InfoContext(ctx, "Request received", "path", "/users")
package devlogs

// Version is the library version.
const Version = "2.0.1"
