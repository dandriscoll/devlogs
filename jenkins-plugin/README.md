# Devlogs Jenkins Plugin

A Jenkins plugin that streams build logs to a [devlogs](https://github.com/dandriscoll/devlogs) OpenSearch instance for enhanced log analysis and debugging during development.

## Features

- **Pipeline-Level Configuration**: Configure once in the `options` block, automatically captures all stages
- **Real-time Log Streaming**: Automatically captures and streams console output to OpenSearch during build execution
- **Non-Intrusive**: If no URL is provided, the plugin does nothing - no impact on builds
- **Batch Processing**: Efficiently batches log entries before sending to reduce network overhead
- **Error Resilient**: Failures to send logs don't cause build failures
- **UI Configuration**: Can also be configured via Jenkins job configuration UI

## Installation

### From Jenkins Update Center

1. Navigate to **Manage Jenkins** → **Manage Plugins**
2. Go to the **Available** tab
3. Search for "Devlogs"
4. Check the box next to the plugin and click **Install without restart**

### Manual Installation

1. Download the latest `.hpi` file from the [releases page](https://github.com/dandriscoll/devlogs/releases)
2. Navigate to **Manage Jenkins** → **Manage Plugins** → **Advanced**
3. Under **Upload Plugin**, choose the downloaded `.hpi` file
4. Click **Upload**
5. Restart Jenkins if required

### Building from Source

```bash
cd jenkins-plugin
mvn clean package
```

The built `.hpi` file will be in `target/devlogs.hpi`.

## Configuration

The plugin requires a devlogs OpenSearch URL in the format:

```
https://user:password@host:port/index
```

### Example URLs

```
https://admin:mypassword@opensearch.example.com:9200/devlogs-myproject
https://admin:p%40ssw0rd%21@localhost:9200/devlogs-dev
```

**Note**: Special characters in passwords must be URL-encoded:
- `!` → `%21`
- `@` → `%40`
- `#` → `%23`
- `$` → `%24`
- `%` → `%25`

Use the devlogs CLI `devlogs mkurl` command to generate properly encoded URLs.

## Usage

### Pipeline-Level Configuration (Recommended)

Add `devlogs` to the `options` block to automatically capture all stages:

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

        stage('Deploy') {
            steps {
                sh './deploy.sh'
            }
        }
    }
}
```

All console output from all stages is automatically streamed to devlogs.

### Minimal Example

```groovy
pipeline {
    agent any

    options {
        devlogs(url: 'https://admin:password@opensearch.example.com:9200/devlogs-myproject')
    }

    stages {
        stage('Build') {
            steps {
                sh 'make build'
            }
        }
    }
}
```

### Conditional Usage

Enable devlogs only when an environment variable is set:

```groovy
pipeline {
    agent any

    environment {
        DEVLOGS_URL = credentials('devlogs-opensearch-url')
    }

    options {
        // Empty string disables devlogs
        devlogs(url: "${env.ENABLE_DEVLOGS == 'true' ? env.DEVLOGS_URL : ''}")
    }

    stages {
        stage('Build') {
            steps {
                sh 'make build'
            }
        }
    }
}
```

### Per-Stage Configuration (Advanced)

For fine-grained control, you can wrap individual stages instead:

```groovy
pipeline {
    agent any

    environment {
        DEVLOGS_URL = credentials('devlogs-opensearch-url')
    }

    stages {
        stage('Build') {
            steps {
                // Only this stage is logged
                devlogs(url: env.DEVLOGS_URL) {
                    sh 'npm install'
                    sh 'npm run build'
                }
            }
        }

        stage('Deploy') {
            steps {
                // This stage is NOT logged
                sh './deploy.sh'
            }
        }
    }
}
```

### Jenkins UI Configuration

You can also configure devlogs via the Jenkins job configuration UI:

1. Open your job configuration
2. Under **Build Environment**, check **Stream logs to Devlogs**
3. Enter your devlogs URL
4. Save

### In Scripted Pipeline

```groovy
node {
    // Wrap entire node block
    wrap([$class: 'DevlogsBuildWrapper', url: 'https://admin:password@opensearch.example.com:9200/devlogs-myproject']) {
        stage('Build') {
            sh 'make build'
            sh 'make test'
        }
    }
}
```

### Without URL (Pass-through)

If no URL is provided, the plugin acts as a pass-through and doesn't send any logs:

```groovy
options {
    devlogs(url: '')  // Disabled
}
```

## Log Format

The plugin sends logs to OpenSearch in the following format:

```json
{
  "doc_type": "log_entry",
  "timestamp": "2026-01-12T05:30:00.000Z",
  "run_id": "jenkins-myproject-main-123",
  "job": "myproject/main",
  "build_number": 123,
  "build_url": "job/myproject/job/main/123/",
  "seq": 1,
  "message": "Building project...",
  "source": "jenkins",
  "level": "info"
}
```

### Fields

- `doc_type`: Always "log_entry"
- `timestamp`: ISO 8601 timestamp when the log was captured
- `run_id`: Unique identifier for the build run
- `job`: Full job name including folder path
- `build_number`: Build number
- `build_url`: Relative URL to the build
- `seq`: Sequence number (1, 2, 3, ...) for ordering logs
- `message`: The actual log line content
- `source`: Always "jenkins"
- `level`: Log level (currently always "info")

## Viewing Logs

After logs are streamed to devlogs, you can view them using:

### Devlogs CLI

```bash
# Tail logs for a specific build
devlogs tail --area jenkins --run-id jenkins-myproject-main-123

# Search logs
devlogs search --q "error" --area jenkins

# Follow logs in real-time
devlogs tail --area jenkins --follow
```

### Devlogs Web UI

```bash
# Start the web UI
devlogs web --port 8088

# Open http://localhost:8088/ui/
# Search for: source:jenkins
```

## Troubleshooting

### Logs Not Appearing in Devlogs

1. **Verify OpenSearch connection**: Test your URL with the devlogs CLI:
   ```bash
   devlogs --url 'https://admin:pass@host:9200/index' diagnose
   ```

2. **Check URL encoding**: Ensure special characters in passwords are URL-encoded

3. **Verify index exists**: Make sure the index specified in the URL exists:
   ```bash
   devlogs --url 'https://admin:pass@host:9200/index' init
   ```

4. **Check Jenkins console output**: Look for warning messages like:
   ```
   Warning: Failed to send log to devlogs: Connection refused
   ```

### Authentication Errors

If you see authentication-related errors, verify:
- Username and password are correct
- Password special characters are URL-encoded
- User has write permissions to the index

### Network Errors

If you see connection errors:
- Ensure OpenSearch is accessible from Jenkins agents
- Check firewall rules
- Verify the hostname/IP and port are correct

## Performance Considerations

The plugin is designed to have minimal impact on build performance:

- **Batching**: Logs are batched (default 10 lines or 10 seconds) before sending
- **Non-blocking**: Log streaming happens asynchronously
- **Error handling**: Network failures don't block the build
- **Lightweight**: No heavy processing or transformation of logs

## Comparison with CLI Approach

This plugin differs from the `devlogs jenkins` CLI command approach:

| Feature | Plugin | CLI |
|---------|--------|-----|
| Installation | Via Jenkins Update Center | Download binary, add to pipeline |
| Configuration | Per-pipeline URL in options | Environment variable |
| Integration | Native Jenkins step | External binary |
| Updates | Via Jenkins plugin updates | Manual binary updates |
| Resource usage | Runs in Jenkins JVM | Separate process |

## Development

### Building

```bash
cd jenkins-plugin
mvn clean package
```

### Testing

```bash
mvn test
```

### Running in Test Jenkins

```bash
mvn hpi:run
```

This will start a test Jenkins instance at http://localhost:8080/jenkins

### Code Style

This plugin follows the [Jenkins plugin development guidelines](https://www.jenkins.io/doc/developer/plugin-development/) and uses standard Maven formatting.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure `mvn test` passes
6. Submit a pull request

## License

MIT License - see [LICENSE](../LICENSE) file for details.

## See Also

- [Devlogs Project](https://github.com/dandriscoll/devlogs)
- [Jenkins Plugin Tutorial](https://www.jenkins.io/doc/developer/tutorial/)
- [Pipeline Syntax](https://www.jenkins.io/doc/book/pipeline/syntax/)
