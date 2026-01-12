# Jenkins Plugin Quick Start Guide

This guide will help you get started with the Devlogs Jenkins Plugin.

## What is the Devlogs Jenkins Plugin?

The Devlogs Jenkins Plugin is a native Jenkins plugin that streams build console output in real-time to a devlogs OpenSearch instance. Unlike the CLI-based approach (`devlogs jenkins attach`), this plugin integrates directly into Jenkins and provides a simpler, more native experience.

## Key Features

✅ **Native Jenkins Integration** - Install via Jenkins Update Center  
✅ **Per-Pipeline Configuration** - Different URL for each pipeline  
✅ **Non-Intrusive** - No URL = no logging (zero impact)  
✅ **Error Resilient** - Logging failures don't break builds  
✅ **Batch Processing** - Efficient log streaming  
✅ **Easy to Use** - Simple `devlogs { }` wrapper syntax  

## Quick Start

### 1. Prerequisites

- Jenkins 2.440.3 or higher
- Java 11 or higher
- A running devlogs OpenSearch instance
- Network access from Jenkins agents to OpenSearch

### 2. Build the Plugin

Since the Jenkins repository is blocked in the build environment, you'll need to build the plugin in an environment with internet access:

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
    
    stages {
        stage('Build') {
            steps {
                devlogs(url: env.DEVLOGS_URL) {
                    sh 'npm install'
                    sh 'npm run build'
                }
            }
        }
    }
}
```

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

- **Jenkinsfile.simple** - Basic usage
- **Jenkinsfile.credentials** - Using Jenkins credentials
- **Jenkinsfile.conditional** - Only log development branches
- **Jenkinsfile** - Complete example with multiple stages

## Comparison: Plugin vs CLI

| Feature | Plugin | CLI (`devlogs jenkins`) |
|---------|--------|------------------------|
| Installation | Jenkins Update Center | Download binary |
| Configuration | Per-pipeline in Jenkinsfile | Environment variables |
| Syntax | `devlogs(url: '...') { }` | `sh 'devlogs jenkins attach'` |
| Updates | Via Jenkins | Manual binary update |
| Integration | Native Jenkins step | External process |

## Common Issues

### Build fails with "devlogs: command not found"

This means you're trying to use the CLI approach, not the plugin. Change from:

```groovy
sh 'devlogs jenkins attach --background'
```

To:

```groovy
devlogs(url: credentials('devlogs-url')) {
    // your build steps
}
```

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
