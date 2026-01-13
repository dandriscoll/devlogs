package devlogs

import "fmt"

// OpenSearchError is the base error type for OpenSearch operations.
type OpenSearchError struct {
	Message string
	Cause   error
}

func (e *OpenSearchError) Error() string {
	if e.Cause != nil {
		return fmt.Sprintf("%s: %v", e.Message, e.Cause)
	}
	return e.Message
}

func (e *OpenSearchError) Unwrap() error {
	return e.Cause
}

// ConnectionError indicates a connection failure to OpenSearch.
type ConnectionError struct {
	OpenSearchError
}

// NewConnectionError creates a new ConnectionError.
func NewConnectionError(message string, cause error) *ConnectionError {
	return &ConnectionError{
		OpenSearchError: OpenSearchError{Message: message, Cause: cause},
	}
}

// AuthError indicates authentication failure (HTTP 401).
type AuthError struct {
	OpenSearchError
}

// NewAuthError creates a new AuthError.
func NewAuthError(message string) *AuthError {
	return &AuthError{
		OpenSearchError: OpenSearchError{Message: message},
	}
}

// IndexNotFoundError indicates the index does not exist (HTTP 404).
type IndexNotFoundError struct {
	OpenSearchError
}

// NewIndexNotFoundError creates a new IndexNotFoundError.
func NewIndexNotFoundError(indexName string) *IndexNotFoundError {
	return &IndexNotFoundError{
		OpenSearchError: OpenSearchError{
			Message: fmt.Sprintf("index '%s' does not exist", indexName),
		},
	}
}

// QueryError indicates a malformed query (HTTP 400).
type QueryError struct {
	OpenSearchError
}

// NewQueryError creates a new QueryError.
func NewQueryError(message string) *QueryError {
	return &QueryError{
		OpenSearchError: OpenSearchError{Message: message},
	}
}
