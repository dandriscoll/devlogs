# Jenkins Plugin Quick Start Guide

This guide will help you get started with the Devlogs Jenkins Plugin.

## What is the Devlogs Jenkins Plugin?

The Devlogs Jenkins Plugin is a native Jenkins plugin that streams build console output in real-time to a devlogs OpenSearch instance. Configure it once at the pipeline level and all stages are automatically captured.

## Key Features

- **Pipeline-Level Configuration** - Set once in `options {}`, captures all stages
- **Native Jenkins Integration** - Install via Jenkins Update Center
- **Non-Intrusive** - No URL = no logging (zero impact)
- **Error Resilient** - Logging failures don't break builds
- **Batch Processing** - Efficient log streaming
- **UI Configuration** - Can also configure via Jenkins job settings

## Quick Start

### 1. Prerequisites

- Jenkins 2.440.3 or higher
- Java 11 or higher
- A running devlogs OpenSearch instance
- Network access from Jenkins agents to OpenSearch

### 2. Build the Plugin

```bash
cd jenkins-plugin
mvn clean package
```

The built plugin will be at `target/devlogs.hpi`

### 3. Install the Plugin

**Option A: Via Jenkins UI (Recommended)**

1. Go to **Manage Jenkins** → **Manage Plugins** → **Advanced**
2. Under **Upload Plugin**, choose `target/devlogs.hpi`
3. Click **Upload**
4. Restart Jenkins when prompted

**Option B: Manual Installation**

```bash
# Copy to Jenkins plugins directory
cp target/devlogs.hpi $JENKINS_HOME/plugins/
# Restart Jenkins
systemctl restart jenkins
```

### 4. Configure Jenkins Credentials

Store your devlogs OpenSearch URL as a Jenkins credential:

1. Go to **Manage Jenkins** → **Manage Credentials**
2. Click **(global)** domain
3. Click **Add Credentials**
4. Select **Secret text**
5. In **Secret**, enter your URL:
   ```
   https://admin:password@opensearch.example.com:9200/devlogs-myproject
   ```
6. In **ID**, enter: `devlogs-opensearch-url`
7. Click **Create**

**Important**: Special characters in passwords must be URL-encoded. Use `devlogs mkurl` to generate properly encoded URLs.

### 5. Use in Jenkinsfile

**Simple Example:**

```groovy
pipeline {
    agent any

    environment {
        DEVLOGS_URL = credentials('devlogs-opensearch-url')
    }

    options {
        devlogs(url: '${DEVLOGS_URL}')
    }

    stages {
        stage('Build') {
            steps {
                sh 'npm install'
                sh 'npm run build'
            }
        }

        stage('Test') {
            steps {
                sh 'npm test'
            }
        }
    }
}
```

That's it! All console output from all stages is automatically streamed to devlogs.

### 6. View Logs

After your pipeline runs, view the logs using devlogs CLI:

```bash
# Tail logs from Jenkins
devlogs tail --source jenkins --follow

# Search for specific build
devlogs search --q "job:myproject" --source jenkins

# View in web UI
devlogs web --port 8088
# Then visit http://localhost:8088/ui/
```

## Examples

The `jenkins-plugin/examples/` directory contains several example Jenkinsfiles:

- **Jenkinsfile.simple** - Minimal pipeline-level usage
- **Jenkinsfile.credentials** - Using Jenkins credentials
- **Jenkinsfile.conditional** - Enable/disable via environment variable
- **Jenkinsfile.per-stage** - Fine-grained per-stage control (advanced)
- **Jenkinsfile** - Complete example with multiple stages

## Alternative: UI Configuration

You can also configure devlogs via the Jenkins job configuration UI:

1. Open your job configuration
2. Under **Build Environment**, check **Stream logs to Devlogs**
3. Enter your devlogs URL
4. Save

## Comparison: Pipeline Options vs Per-Stage

| Approach | Syntax | Use Case |
|----------|--------|----------|
| Pipeline options | `options { devlogs(url: '...') }` | Capture all stages (recommended) |
| Per-stage wrapper | `devlogs(url: '...') { ... }` | Fine-grained control over what's logged |

## Common Issues

### Logs not appearing in devlogs

1. Check Jenkins console output for warnings
2. Verify OpenSearch is accessible: `devlogs diagnose`
3. Check URL encoding of password
4. Ensure index exists: `devlogs init`

### Authentication errors

Use URL-encoded passwords:
- `!` → `%21`
- `@` → `%40`
- `#` → `%23`

Generate with: `devlogs mkurl`

## Next Steps

- Read the full [README.md](README.md) for detailed documentation
- See [PUBLISHING.md](PUBLISHING.md) to publish to Jenkins Update Center
- Check [CHANGELOG.md](CHANGELOG.md) for version history
- Review examples in `examples/` directory

## Support

- GitHub Issues: https://github.com/dandriscoll/devlogs/issues
- Documentation: [README.md](README.md)
- Examples: [examples/](examples/)
