# Using Devlogs with Jenkins

Stream Jenkins build logs to OpenSearch in near real-time using the Devlogs Jenkins Plugin.

## Prerequisites

1. **Jenkins 2.440.3 or higher**
2. **Java 11 or higher**
3. **OpenSearch URL stored in Jenkins credentials** (Manage Jenkins > Credentials)
   - Add a "Secret text" credential with ID `devlogs-opensearch-url`
   - Value: `opensearchs://user:pass@host:9200/index`
   - **Important:** Special characters in passwords must be URL-encoded (e.g., `!` becomes `%21`)
   - Use `devlogs mkurl` to generate a properly encoded URL

## Quick Start

```groovy
pipeline {
    agent any

    options {
        devlogs(credentialsId: 'devlogs-opensearch-url')
    }

    stages {
        stage('Build') {
            steps {
                sh 'make build'
                sh 'make test'
            }
        }
    }
}
```

For complete plugin documentation, see [jenkins-plugin/README.md](jenkins-plugin/README.md).

## Development Branches Only

To only stream logs for non-production branches, use the `devlogs` step inside a conditional block instead of `options`:

```groovy
pipeline {
    agent any

    environment {
        DEVLOGS_URL = credentials('devlogs-opensearch-url')
    }

    stages {
        stage('Build') {
            steps {
                script {
                    if (env.BRANCH_NAME != 'main' && env.BRANCH_NAME != 'production') {
                        devlogs(url: env.DEVLOGS_URL) {
                            sh 'make build'
                            sh 'make test'
                        }
                    } else {
                        sh 'make build'
                        sh 'make test'
                    }
                }
            }
        }
    }
}
```

## One-Time Log Snapshot (CLI)

To capture logs from a completed build without real-time streaming, use the CLI `jenkins snapshot` command:

```bash
devlogs jenkins snapshot --build-url https://jenkins.example.com/job/my-job/123/
```

This fetches all available console output and indexes it into OpenSearch in a single pass.

## Environment Variables

**Auto-set by Jenkins:**
- `BUILD_URL` - Used to fetch console logs
- `JOB_NAME`, `BUILD_NUMBER`, `BUILD_TAG` - Build metadata
- `BRANCH_NAME`, `GIT_COMMIT` - Git metadata

**Optional authentication (if Jenkins requires it for API access):**
- `JENKINS_USER` - Username for Jenkins API
- `JENKINS_TOKEN` - API token for Jenkins API

## Troubleshooting

### Authentication Failed

If you see "Authentication failed" errors, your password likely contains special characters that need URL encoding:

| Character | URL Encoded |
|-----------|-------------|
| `!` | `%21` |
| `@` | `%40` |
| `#` | `%23` |
| `$` | `%24` |
| `%` | `%25` |
| `:` | `%3A` |
| `/` | `%2F` |

Use the `mkurl` command to generate a properly encoded URL:

```bash
devlogs mkurl
# Choose option 2, enter your components
# Copy the generated URL to Jenkins credentials
```

### Testing the URL

Test your URL locally before adding to Jenkins:

```bash
devlogs --url 'opensearchs://admin:pass%21word@host:9200/index' diagnose
```

### Viewing Streamed Logs

```bash
# In another terminal, tail the logs being streamed
devlogs tail --area jenkins --follow
```
