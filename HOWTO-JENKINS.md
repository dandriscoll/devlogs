# Using Devlogs with Jenkins

Stream Jenkins build logs to OpenSearch in near real-time.

## Prerequisites

1. **Build the standalone binary** (one-time):
   ```sh
   ./build-standalone.sh
   ```
   Then host `dist/devlogs-linux` somewhere accessible (GitHub releases, S3, internal server).

2. **OpenSearch URL stored in Jenkins credentials** (Manage Jenkins > Credentials)
   - Add a "Secret text" credential with ID `devlogs-opensearch-url`
   - Value: `https://user:pass@host:9200/index`
   - **Important:** Special characters in passwords must be URL-encoded (e.g., `!` becomes `%21`)
   - Use `devlogs mkurl` to generate a properly encoded URL

3. **Devlogs binary URL in Jenkins credentials**
   - Add a "Secret text" credential with ID `devlogs-binary-url`
   - Value: URL to your hosted `devlogs-linux` binary

## Quick Start

```groovy
pipeline {
    agent any
    environment {
        DEVLOGS_OPENSEARCH_URL = credentials('devlogs-opensearch-url')
        DEVLOGS_BINARY_URL = credentials('devlogs-binary-url')
    }
    stages {
        stage('Build') {
            steps {
                sh 'curl -sL $DEVLOGS_BINARY_URL -o /tmp/devlogs && chmod +x /tmp/devlogs'
                sh '/tmp/devlogs jenkins attach --background'
                sh 'make build'  // Your build steps
            }
        }
    }
    post {
        always {
            sh '/tmp/devlogs jenkins stop || true'
        }
    }
}
```

## Development Branches Only

To only stream logs for non-production branches:

```groovy
pipeline {
    agent any
    environment {
        DEVLOGS_OPENSEARCH_URL = credentials('devlogs-opensearch-url')
        DEVLOGS_BINARY_URL = credentials('devlogs-binary-url')
    }
    stages {
        stage('Build') {
            steps {
                script {
                    if (env.BRANCH_NAME != 'main' && env.BRANCH_NAME != 'production') {
                        sh 'curl -sL $DEVLOGS_BINARY_URL -o /tmp/devlogs && chmod +x /tmp/devlogs'
                        sh '/tmp/devlogs jenkins attach --background'
                    }
                }
                sh 'make build'
            }
        }
    }
    post {
        always {
            sh '/tmp/devlogs jenkins stop || true'
        }
    }
}
```

## Commands

| Command | Description |
|---------|-------------|
| `devlogs jenkins attach --background` | Stream logs to OpenSearch in background |
| `devlogs jenkins stop` | Stop background streaming |
| `devlogs jenkins snapshot` | One-time log capture (no streaming) |
| `devlogs jenkins status` | Show streaming status |

## Environment Variables

**Auto-set by Jenkins:**
- `BUILD_URL` - Used to fetch console logs
- `JOB_NAME`, `BUILD_NUMBER`, `BUILD_TAG` - Build metadata
- `BRANCH_NAME`, `GIT_COMMIT` - Git metadata

**Optional authentication (if Jenkins requires it):**
- `JENKINS_USER` - Username for Jenkins API
- `JENKINS_TOKEN` - API token for Jenkins API

```groovy
withCredentials([usernamePassword(
    credentialsId: 'devlogs-jenkins',
    usernameVariable: 'JENKINS_USER',
    passwordVariable: 'JENKINS_TOKEN'
)]) {
    sh '/tmp/devlogs jenkins attach --background'
}
```

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
devlogs --url 'https://admin:pass%21word@host:9200/index' diagnose
```

### Viewing Streamed Logs

```bash
# In another terminal, tail the logs being streamed
devlogs tail --area jenkins --follow
```
