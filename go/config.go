package devlogs

import (
	"fmt"
	"net/url"
	"os"
	"strconv"
	"time"

	"github.com/joho/godotenv"
)

// Config holds all devlogs configuration options.
type Config struct {
	Host                   string
	Port                   int
	User                   string
	Password               string
	Timeout                time.Duration
	Index                  string
	CircuitBreakerDuration time.Duration
	ErrorPrintInterval     time.Duration
}

// DefaultConfig returns a Config with default values.
func DefaultConfig() *Config {
	return &Config{
		Host:                   "localhost",
		Port:                   9200,
		User:                   "admin",
		Password:               "admin",
		Timeout:                30 * time.Second,
		Index:                  "devlogs-0001",
		CircuitBreakerDuration: 60 * time.Second,
		ErrorPrintInterval:     10 * time.Second,
	}
}

// LoadConfig loads configuration from environment variables.
// It first attempts to load from .env file if present.
func LoadConfig() (*Config, error) {
	// Try to load .env file (ignore errors if not found)
	_ = godotenv.Load()
	return loadFromEnv()
}

// LoadConfigWithEnvFile loads configuration after reading from a specific .env file.
func LoadConfigWithEnvFile(path string) (*Config, error) {
	if err := godotenv.Load(path); err != nil {
		return nil, fmt.Errorf("failed to load env file %s: %w", path, err)
	}
	return loadFromEnv()
}

func loadFromEnv() (*Config, error) {
	cfg := DefaultConfig()

	// Check for URL shortcut first
	if osURL := os.Getenv("DEVLOGS_OPENSEARCH_URL"); osURL != "" {
		if err := parseOpenSearchURL(osURL, cfg); err != nil {
			return nil, err
		}
	} else {
		// Load individual settings
		if host := os.Getenv("DEVLOGS_OPENSEARCH_HOST"); host != "" {
			cfg.Host = host
		}
		if portStr := os.Getenv("DEVLOGS_OPENSEARCH_PORT"); portStr != "" {
			port, err := strconv.Atoi(portStr)
			if err != nil {
				return nil, fmt.Errorf("invalid DEVLOGS_OPENSEARCH_PORT: %w", err)
			}
			cfg.Port = port
		}
		if user := os.Getenv("DEVLOGS_OPENSEARCH_USER"); user != "" {
			cfg.User = user
		}
		if pass := os.Getenv("DEVLOGS_OPENSEARCH_PASS"); pass != "" {
			cfg.Password = pass
		}
		if index := os.Getenv("DEVLOGS_INDEX"); index != "" {
			cfg.Index = index
		}
	}

	// Timeout can override URL settings
	if timeoutStr := os.Getenv("DEVLOGS_OPENSEARCH_TIMEOUT"); timeoutStr != "" {
		timeout, err := strconv.Atoi(timeoutStr)
		if err != nil {
			return nil, fmt.Errorf("invalid DEVLOGS_OPENSEARCH_TIMEOUT: %w", err)
		}
		cfg.Timeout = time.Duration(timeout) * time.Second
	}

	return cfg, nil
}

// parseOpenSearchURL parses a URL like http://user:pass@host:port/index
func parseOpenSearchURL(rawURL string, cfg *Config) error {
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return fmt.Errorf("invalid DEVLOGS_OPENSEARCH_URL: %w", err)
	}

	if parsed.Scheme != "" && parsed.Scheme != "http" && parsed.Scheme != "https" {
		return fmt.Errorf("invalid URL scheme '%s': must be 'http' or 'https'", parsed.Scheme)
	}

	if parsed.Hostname() == "" {
		return fmt.Errorf("invalid URL: missing hostname")
	}

	cfg.Host = parsed.Hostname()

	if parsed.Port() != "" {
		port, err := strconv.Atoi(parsed.Port())
		if err != nil {
			return fmt.Errorf("invalid port in URL: %w", err)
		}
		cfg.Port = port
	} else if parsed.Scheme == "https" {
		cfg.Port = 443
	}

	if parsed.User != nil {
		cfg.User = parsed.User.Username()
		if pass, ok := parsed.User.Password(); ok {
			cfg.Password = pass
		}
	}

	// Path is the index name (strip leading slash)
	if len(parsed.Path) > 1 {
		cfg.Index = parsed.Path[1:]
	}

	return nil
}

// BaseURL returns the OpenSearch base URL.
func (c *Config) BaseURL() string {
	return fmt.Sprintf("http://%s:%d", c.Host, c.Port)
}
