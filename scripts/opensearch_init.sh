#!/bin/bash
# Initialize OpenSearch indices/templates
set -e
HOST=${OPENSEARCH_HOST:-localhost}
PORT=${OPENSEARCH_PORT:-9200}
USER=${OPENSEARCH_USER:-admin}
PASS=${OPENSEARCH_PASS:-admin}

echo "Creating index templates..."
curl -u "$USER:$PASS" -XPUT "http://$HOST:$PORT/_index_template/devlogs-logs-template" -H 'Content-Type: application/json' --data-binary @"$(dirname "$0")/../src/devlogs/opensearch/mappings.py"

echo "Creating initial indices..."
curl -u "$USER:$PASS" -XPUT "http://$HOST:$PORT/devlogs-logs-0001"
echo "Done."
