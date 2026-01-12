---
title: devlogs
summary: Forwards all of your application's logs to opensearch so that an LLM can easily crawl and search them. Enables hypervelocity coding loops.
icon: devlogs.png
shipped: 2025-12-22
author:
  name: Dan Driscoll
  github: dandriscoll
---

devlogs began from a desire to have my coding agent easily read application logs. They were getting send everywhere - HTTP logs, console, Jenkins logs, browser logs. I wanted an easy way to collect them all.

OpenSearch is easy to set up locally and can quickly serve up logs. The MCP tooling lets the agent query around the index for recent failures, areas of the code, operation IDs, and whatever else it needs.

The devlogs CLI ended up being really handy to get the system online and running.