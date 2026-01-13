package devlogs

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

// Client is the OpenSearch HTTP client.
type Client struct {
	baseURL    string
	authHeader string
	httpClient *http.Client
	indexName  string
}

// NewClient creates a new OpenSearch client from config.
func NewClient(cfg *Config) *Client {
	authStr := base64.StdEncoding.EncodeToString(
		[]byte(cfg.User + ":" + cfg.Password),
	)

	return &Client{
		baseURL:    cfg.BaseURL(),
		authHeader: "Basic " + authStr,
		httpClient: &http.Client{
			Timeout: cfg.Timeout,
		},
		indexName: cfg.Index,
	}
}

// Index sends a document to OpenSearch.
func (c *Client) Index(ctx context.Context, doc interface{}) error {
	jsonData, err := json.Marshal(doc)
	if err != nil {
		return fmt.Errorf("failed to marshal document: %w", err)
	}

	url := fmt.Sprintf("%s/%s/_doc", c.baseURL, c.indexName)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(jsonData))
	if err != nil {
		return NewConnectionError("failed to create request", err)
	}

	req.Header.Set("Authorization", c.authHeader)
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return NewConnectionError(fmt.Sprintf("cannot connect to OpenSearch at %s", c.baseURL), err)
	}
	defer resp.Body.Close()

	// Read body for error messages
	body, _ := io.ReadAll(resp.Body)

	switch resp.StatusCode {
	case http.StatusOK, http.StatusCreated:
		return nil
	case http.StatusUnauthorized:
		return NewAuthError("authentication failed (HTTP 401)")
	case http.StatusNotFound:
		return NewIndexNotFoundError(c.indexName)
	case http.StatusBadRequest:
		return NewQueryError(fmt.Sprintf("bad request: %s", string(body)))
	default:
		return NewConnectionError(
			fmt.Sprintf("unexpected status %d: %s", resp.StatusCode, string(body)),
			nil,
		)
	}
}

// IndexName returns the configured index name.
func (c *Client) IndexName() string {
	return c.indexName
}
