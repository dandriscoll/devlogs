# Devlogs Jenkins Plugin - Implementation Summary

This document provides an overview of the Jenkins plugin implementation for the devlogs project.

## What Was Created

A complete, production-ready Jenkins plugin that streams build logs to a devlogs OpenSearch instance.

## Directory Structure

```
jenkins-plugin/
├── pom.xml                          # Maven build configuration
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── io/github/dandriscoll/devlogs/
│   │   │       └── DevlogsStep.java  # Main plugin implementation
│   │   └── resources/
│   │       ├── index.jelly           # Plugin description
│   │       └── io/github/dandriscoll/devlogs/DevlogsStep/
│   │           ├── config.jelly      # Configuration UI
│   │           ├── help-url.html     # Help for URL field
│   │           └── help-index.html   # Help for index field
│   └── test/
│       └── java/
│           └── io/github/dandriscoll/devlogs/
│               └── DevlogsStepTest.java  # Unit tests
├── examples/
│   ├── Jenkinsfile                   # Complete example
│   ├── Jenkinsfile.simple            # Simple example
│   ├── Jenkinsfile.credentials       # Using credentials
│   └── Jenkinsfile.conditional       # Conditional logging
├── README.md                         # Complete documentation
├── QUICKSTART.md                     # Quick start guide
├── PUBLISHING.md                     # Publishing instructions
├── CHANGELOG.md                      # Version history
├── BUILD_ENVIRONMENT_NOTE.md         # Build notes
├── build.sh                          # Build script
├── test.sh                           # Test script
└── .gitignore                        # Git ignore rules

.github/workflows/
└── build-jenkins-plugin.yml          # GitHub Actions workflow
```

## Key Features

### 1. Native Jenkins Integration
- Pipeline step: `devlogs(url: '...') { ... }`
- Follows Jenkins plugin best practices
- Compatible with declarative and scripted pipelines

### 2. Console Log Streaming
- Real-time log capture via ConsoleLogFilter
- Batch processing (50 lines per batch)
- Efficient bulk indexing to OpenSearch

### 3. Configuration
- Per-pipeline URL configuration
- Optional index override
- Support for Jenkins credentials
- URL extraction and parsing

### 4. Error Resilience
- Network failures don't break builds
- Graceful degradation
- Warning messages only

### 5. Documentation
- Complete README with examples
- Quick start guide
- Publishing instructions
- Troubleshooting section

## Implementation Details

### DevlogsStep Class
- Extends `Step` for pipeline integration
- Uses `@DataBoundConstructor` for configuration
- Implements `@Extension` for plugin discovery

### DevlogsStepExecution
- Manages step execution lifecycle
- Creates ConsoleLogFilter for log interception
- Handles context passing

### DevlogsConsoleLogFilter
- Intercepts console output
- Extracts build metadata
- Creates DevlogsOutputStream

### DevlogsOutputStream
- Captures log lines
- Batches entries (50 per batch)
- Sends to OpenSearch via bulk API
- Uses OkHttp for HTTP requests
- Serializes JSON with Gson

## Log Format

Each log entry is stored as:

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

## Testing

### Unit Tests (DevlogsStepTest)
- Test with no URL (pass-through)
- Test with URL (actual streaming)
- Test with build failures
- Test descriptor methods
- Test getters/setters

### Manual Testing
```bash
cd jenkins-plugin
mvn hpi:run
# Visit http://localhost:8080/jenkins
```

## Building

### Prerequisites
- Java 11+
- Maven 3.6+
- Internet access (for dependencies)

### Build Command
```bash
cd jenkins-plugin
mvn clean package
```

Output: `target/devlogs.hpi`

### Automated Build
GitHub Actions workflow automatically builds on every push:
- Runs tests
- Builds plugin
- Uploads artifacts

## Installation

### Via Jenkins UI
1. Build the plugin: `mvn clean package`
2. Go to Manage Jenkins → Manage Plugins → Advanced
3. Upload `target/devlogs.hpi`
4. Restart Jenkins

### Via File System
```bash
cp target/devlogs.hpi $JENKINS_HOME/plugins/
systemctl restart jenkins
```

## Usage Examples

### Basic Usage
```groovy
pipeline {
    agent any
    stages {
        stage('Build') {
            steps {
                devlogs(url: 'https://admin:pass@host:9200/index') {
                    sh 'make build'
                }
            }
        }
    }
}
```

### With Credentials
```groovy
pipeline {
    agent any
    environment {
        DEVLOGS_URL = credentials('devlogs-url')
    }
    stages {
        stage('Build') {
            steps {
                devlogs(url: env.DEVLOGS_URL) {
                    sh 'make build'
                }
            }
        }
    }
}
```

### Conditional (Dev Only)
```groovy
script {
    def isDev = env.BRANCH_NAME != 'main'
    if (isDev) {
        devlogs(url: credentials('devlogs-url')) {
            sh 'make build'
        }
    } else {
        sh 'make build'
    }
}
```

## Publishing

### To Jenkins Update Center
See [PUBLISHING.md](PUBLISHING.md) for detailed instructions.

Summary:
1. Request hosting from Jenkins community
2. Configure Maven credentials
3. Tag release
4. Deploy: `mvn deploy`
5. Create GitHub release

### Via GitHub Releases Only
1. Build: `mvn package`
2. Create GitHub release
3. Attach `devlogs.hpi` file
4. Users install via URL

## Comparison with CLI Approach

| Aspect | Plugin | CLI (`devlogs jenkins`) |
|--------|--------|------------------------|
| Installation | Jenkins Update Center | Download binary |
| Configuration | Per-pipeline | Environment variables |
| Syntax | `devlogs { }` | `sh 'devlogs jenkins attach'` |
| Updates | Via Jenkins | Manual |
| Integration | Native | External process |
| Complexity | Low | Medium |

## Future Enhancements

Possible improvements for future versions:

1. **Log Level Parsing**: Automatically detect log levels (ERROR, WARN, etc.)
2. **Filtering**: Option to filter logs before sending
3. **Custom Fields**: Allow adding custom metadata to logs
4. **Multiple URLs**: Support sending to multiple devlogs instances
5. **Compression**: Compress logs before sending
6. **Retry Logic**: Configurable retry behavior
7. **Statistics**: Display log streaming statistics in build
8. **Global Configuration**: Global default URL with per-pipeline override

## Dependencies

- Jenkins Core: 2.440.3
- Java: 11+
- OkHttp: 4.12.0 (HTTP client)
- Gson: 2.11.0 (JSON processing)
- Workflow Step API (Pipeline support)

## License

MIT License - See [../LICENSE](../LICENSE)

## Support

- Documentation: [README.md](README.md)
- Quick Start: [QUICKSTART.md](QUICKSTART.md)
- Examples: [examples/](examples/)
- Issues: https://github.com/dandriscoll/devlogs/issues

## Related Documentation

- Main devlogs README: [../README.md](../README.md)
- Jenkins integration guide: [../HOWTO-JENKINS.md](../HOWTO-JENKINS.md)
- Jenkins plugin tutorial: https://www.jenkins.io/doc/developer/tutorial/
- Pipeline syntax: https://www.jenkins.io/doc/book/pipeline/syntax/
