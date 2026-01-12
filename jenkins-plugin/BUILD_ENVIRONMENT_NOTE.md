# Build Environment Note

## Important: Building the Plugin

Due to network restrictions in the automated build environment, the plugin **cannot be built automatically** as part of this PR. The Jenkins Maven repository (repo.jenkins-ci.org) is blocked.

## How to Build

To build the plugin, you need an environment with internet access:

### Prerequisites
- Java 11 or higher
- Maven 3.6 or higher
- Internet access to Maven Central and Jenkins repositories

### Build Steps

```bash
cd jenkins-plugin

# Build without tests (if you want to test manually)
mvn clean package -DskipTests

# Or build with tests
mvn clean package
```

The plugin file will be created at: `jenkins-plugin/target/devlogs.hpi`

### Quick Build Script

Use the provided build script:

```bash
cd jenkins-plugin
./build.sh
```

## Testing the Plugin

### Automated Tests

```bash
cd jenkins-plugin
mvn test
```

Or use the test script:

```bash
cd jenkins-plugin
./test.sh
```

### Manual Testing

Run a test Jenkins instance:

```bash
cd jenkins-plugin
mvn hpi:run
```

Then visit http://localhost:8080/jenkins and create a test pipeline to verify functionality.

## Why This Limitation Exists

The automated build environment has restricted network access for security reasons. The following domains are blocked:
- repo.jenkins-ci.org (Jenkins plugin repository)
- Other Jenkins-specific Maven repositories

This is a security feature of the build environment and not a problem with the plugin code.

## Verification

Once you build the plugin in your environment, you can verify it works by:

1. **Installing it in Jenkins**:
   - Go to Manage Jenkins → Manage Plugins → Advanced
   - Upload the `devlogs.hpi` file
   - Restart Jenkins

2. **Creating a test pipeline**:
   ```groovy
   pipeline {
       agent any
       stages {
           stage('Test') {
               steps {
                   devlogs(url: 'https://admin:pass@localhost:9200/test') {
                       echo 'Hello from devlogs!'
                   }
               }
           }
       }
   }
   ```

3. **Checking the logs**:
   - Build should succeed
   - Console output should appear normally
   - If OpenSearch is accessible, logs will be sent (check with `devlogs tail`)
   - If OpenSearch is not accessible, build will still succeed (error resilient)

## CI/CD Integration

For continuous integration, you can add a GitHub Actions workflow that builds the plugin:

```yaml
name: Build Jenkins Plugin

on:
  push:
    branches: [ main ]
    paths:
      - 'jenkins-plugin/**'
  pull_request:
    paths:
      - 'jenkins-plugin/**'

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up JDK 11
        uses: actions/setup-java@v4
        with:
          java-version: '11'
          distribution: 'temurin'
          cache: maven
      
      - name: Build and test
        run: |
          cd jenkins-plugin
          mvn clean test package
      
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: devlogs-jenkins-plugin
          path: jenkins-plugin/target/devlogs.hpi
```

This will build the plugin automatically on every push and make the `.hpi` file available as a downloadable artifact.
