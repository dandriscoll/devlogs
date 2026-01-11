# Using Devlogs with Jenkins

Stream Jenkins build logs to OpenSearch in near real-time.

## Prerequisites

**OpenSearch URL stored in Jenkins credentials** (Manage Jenkins > Credentials)
- Add a "Secret text" credential with ID `devlogs-opensearch-url`
- Value: `https://user:pass@host:9200`

## Quick Start

```groovy
pipeline {
    agent any
    environment {
        DEVLOGS_OPENSEARCH_URL = credentials('devlogs-opensearch-url')
    }
    stages {
        stage('Build') {
            steps {
                sh 'pip install --user devlogs && devlogs jenkins attach --background'
                sh 'make build'  // Your build steps
            }
        }
    }
    post {
        always {
            sh 'devlogs jenkins stop || true'
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
    }
    stages {
        stage('Build') {
            steps {
                script {
                    if (env.BRANCH_NAME != 'main' && env.BRANCH_NAME != 'production') {
                        sh 'pip install --user devlogs && devlogs jenkins attach --background'
                    }
                }
                sh 'make build'
            }
        }
    }
    post {
        always {
            sh 'devlogs jenkins stop || true'
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
    sh 'pip install --user devlogs && devlogs jenkins attach --background'
}
```
