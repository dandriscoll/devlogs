#!/bin/bash
# Stop OpenSearch Docker
if [ -f docker-compose.yml ]; then
	docker-compose down
else
	docker stop opensearch-devlogs && docker rm opensearch-devlogs
fi
