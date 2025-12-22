#!/bin/bash
# Start OpenSearch via Docker Compose or docker run
if [ -f docker-compose.yml ]; then
	docker-compose up -d opensearch
else
	docker run -d --name opensearch-devlogs -p 9200:9200 -e "discovery.type=single-node" -e "OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m" -e "plugins.security.disabled=true" opensearchproject/opensearch:latest
fi
