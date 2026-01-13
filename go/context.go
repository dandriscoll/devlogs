package devlogs

import (
	"context"
	"crypto/rand"
	"fmt"
	"sync"
)

type contextKey string

const (
	operationIDKey contextKey = "devlogs_operation_id"
	areaKey        contextKey = "devlogs_area"
)

var (
	globalArea   string
	globalAreaMu sync.RWMutex
)

// WithOperation returns a new context with operation_id and area set.
// If operationID is empty, generates a new UUID.
// If area is empty, preserves existing area from context or uses global area.
func WithOperation(ctx context.Context, operationID, area string) context.Context {
	if operationID == "" {
		operationID = generateUUID()
	}
	ctx = context.WithValue(ctx, operationIDKey, operationID)
	if area != "" {
		ctx = context.WithValue(ctx, areaKey, area)
	}
	return ctx
}

// WithOperationID returns a context with only operation_id set.
func WithOperationID(ctx context.Context, operationID string) context.Context {
	if operationID == "" {
		operationID = generateUUID()
	}
	return context.WithValue(ctx, operationIDKey, operationID)
}

// WithArea returns a context with area set.
func WithArea(ctx context.Context, area string) context.Context {
	return context.WithValue(ctx, areaKey, area)
}

// GetOperationID retrieves the operation_id from context.
func GetOperationID(ctx context.Context) string {
	if v := ctx.Value(operationIDKey); v != nil {
		if s, ok := v.(string); ok {
			return s
		}
	}
	return ""
}

// GetArea retrieves the area from context, falling back to global area.
func GetArea(ctx context.Context) string {
	if v := ctx.Value(areaKey); v != nil {
		if s, ok := v.(string); ok && s != "" {
			return s
		}
	}
	return GetGlobalArea()
}

// SetArea sets the global area for all contexts.
func SetArea(area string) {
	globalAreaMu.Lock()
	defer globalAreaMu.Unlock()
	globalArea = area
}

// GetGlobalArea returns the current global area.
func GetGlobalArea() string {
	globalAreaMu.RLock()
	defer globalAreaMu.RUnlock()
	return globalArea
}

// generateUUID generates a random UUID v4.
func generateUUID() string {
	var uuid [16]byte
	_, _ = rand.Read(uuid[:])
	uuid[6] = (uuid[6] & 0x0f) | 0x40 // Version 4
	uuid[8] = (uuid[8] & 0x3f) | 0x80 // Variant 10
	return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x",
		uuid[0:4], uuid[4:6], uuid[6:8], uuid[8:10], uuid[10:16])
}
