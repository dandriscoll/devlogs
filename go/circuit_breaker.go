package devlogs

import (
	"fmt"
	"os"
	"sync"
	"time"
)

// CircuitBreaker prevents cascade failures when OpenSearch is unavailable.
type CircuitBreaker struct {
	mu               sync.Mutex
	isOpen           bool
	openUntil        time.Time
	lastErrorPrinted time.Time
	duration         time.Duration
	errorInterval    time.Duration
}

var (
	defaultBreaker     *CircuitBreaker
	defaultBreakerOnce sync.Once
)

// DefaultCircuitBreaker returns the shared circuit breaker instance.
func DefaultCircuitBreaker() *CircuitBreaker {
	defaultBreakerOnce.Do(func() {
		defaultBreaker = NewCircuitBreaker(60*time.Second, 10*time.Second)
	})
	return defaultBreaker
}

// NewCircuitBreaker creates a new circuit breaker with custom durations.
func NewCircuitBreaker(duration, errorInterval time.Duration) *CircuitBreaker {
	return &CircuitBreaker{
		duration:      duration,
		errorInterval: errorInterval,
	}
}

// IsOpen checks if the circuit breaker is currently open.
func (cb *CircuitBreaker) IsOpen() bool {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	if !cb.isOpen {
		return false
	}

	// Check if duration has expired
	if time.Now().After(cb.openUntil) {
		return false
	}

	return true
}

// RecordFailure opens the circuit breaker after a failure.
func (cb *CircuitBreaker) RecordFailure(err error) {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	now := time.Now()
	cb.isOpen = true
	cb.openUntil = now.Add(cb.duration)

	// Throttle error printing
	if now.Sub(cb.lastErrorPrinted) > cb.errorInterval {
		fmt.Fprintf(os.Stderr, "[devlogs] Failed to index log, pausing indexing for %.0fs: %v\n",
			cb.duration.Seconds(), err)
		cb.lastErrorPrinted = now
	}
}

// RecordSuccess closes the circuit breaker on successful operation.
func (cb *CircuitBreaker) RecordSuccess() {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	if cb.isOpen {
		cb.isOpen = false
		fmt.Fprintf(os.Stderr, "[devlogs] Connection restored, resuming indexing\n")
	}
}
