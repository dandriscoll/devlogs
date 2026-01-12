# Publishing the Devlogs Jenkins Plugin

This guide covers how to publish the Devlogs Jenkins plugin to various distribution channels.

## Prerequisites

Before publishing, ensure you have:

1. **Jenkins Account**: Register at https://accounts.jenkins.io/
2. **GitHub Account**: With access to the dandriscoll/devlogs repository
3. **Maven Credentials**: Configure Jenkins plugin hosting credentials
4. **GPG Key**: For signing releases (optional but recommended)

## Publishing to Jenkins Update Center

The Jenkins Update Center is the primary distribution channel for Jenkins plugins.

### Initial Setup (One-time)

1. **Request Hosting**:
   - Fork the [jenkinsci/hosting-request](https://github.com/jenkinsci/hosting-request) repository
   - Create a new hosting request following the template
   - Submit a pull request
   - Wait for approval from Jenkins infrastructure team

2. **Configure Maven Settings**:
   
   Add to `~/.m2/settings.xml`:
   
   ```xml
   <settings>
     <servers>
       <server>
         <id>maven.jenkins-ci.org</id>
         <username>YOUR_JENKINS_USERNAME</username>
         <password>YOUR_JENKINS_PASSWORD</password>
       </server>
     </servers>
   </settings>
   ```

3. **Join Jenkins Developers Group**:
   - Request membership at https://accounts.jenkins.io/
   - Wait for approval

### Release Process

#### 1. Prepare Release

```bash
cd jenkins-plugin

# Ensure clean working directory
git status

# Update version in pom.xml (remove -SNAPSHOT)
# Edit pom.xml: change version from 1.0.0-SNAPSHOT to 1.0.0

# Commit version change
git add pom.xml
git commit -m "Prepare release 1.0.0"
```

#### 2. Build and Test

```bash
# Clean build
mvn clean

# Run tests
mvn test

# Build the plugin
mvn package

# Test the built plugin
mvn hpi:run
# Manually test functionality at http://localhost:8080/jenkins
```

#### 3. Create Git Tag

```bash
# Tag the release
git tag -a v1.0.0 -m "Release version 1.0.0"

# Push tag
git push origin v1.0.0
```

#### 4. Deploy to Jenkins Maven Repository

```bash
# Deploy the release
mvn deploy

# This uploads the .hpi file to repo.jenkins-ci.org
```

#### 5. Update Version for Next Development

```bash
# Update to next SNAPSHOT version
# Edit pom.xml: change version from 1.0.0 to 1.0.1-SNAPSHOT

# Commit
git add pom.xml
git commit -m "Prepare for next development iteration"
git push origin main
```

#### 6. Create GitHub Release

1. Go to https://github.com/dandriscoll/devlogs/releases
2. Click "Create a new release"
3. Select the tag (v1.0.0)
4. Title: "Devlogs Jenkins Plugin v1.0.0"
5. Description: Include changelog and features
6. Attach the `.hpi` file from `target/devlogs.hpi`
7. Click "Publish release"

### Automated Release with GitHub Actions

Create `.github/workflows/release-jenkins-plugin.yml`:

```yaml
name: Release Jenkins Plugin

on:
  push:
    tags:
      - 'jenkins-plugin-v*'

jobs:
  release:
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
      
      - name: Deploy to Jenkins Maven Repository
        run: |
          cd jenkins-plugin
          mvn deploy
        env:
          MAVEN_USERNAME: ${{ secrets.JENKINS_USERNAME }}
          MAVEN_PASSWORD: ${{ secrets.JENKINS_PASSWORD }}
      
      - name: Create GitHub Release
        uses: softprops/action-gh-release@v1
        with:
          files: jenkins-plugin/target/devlogs.hpi
          generate_release_notes: true
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Publishing to GitHub Releases Only

If you want to distribute the plugin via GitHub Releases without going through the Jenkins Update Center:

### Manual Process

```bash
cd jenkins-plugin

# Build the plugin
mvn clean package

# The .hpi file is in target/devlogs.hpi
# Upload this to GitHub Releases manually
```

### Automated with GitHub Actions

Create `.github/workflows/build-jenkins-plugin.yml`:

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

## Version Numbering

Follow [Semantic Versioning](https://semver.org/):

- **MAJOR.MINOR.PATCH** (e.g., 1.0.0)
- **MAJOR**: Breaking changes
- **MINOR**: New features, backwards compatible
- **PATCH**: Bug fixes, backwards compatible

## Plugin Distribution via URL

Users can install directly from a URL:

1. Build the plugin: `mvn package`
2. Host `target/devlogs.hpi` on a web server
3. Users install via:
   - **Manage Jenkins** → **Manage Plugins** → **Advanced**
   - Enter URL in **Upload Plugin** section
   - Click **Install**

## Testing Releases

Before publishing, test the release:

### Local Testing

```bash
# Run test Jenkins instance
mvn hpi:run

# Access at http://localhost:8080/jenkins
# Create test pipelines and verify functionality
```

### Test Installation from .hpi

```bash
# Build
mvn package

# Manual installation:
# 1. Copy target/devlogs.hpi to Jenkins
# 2. Install via Manage Plugins → Advanced → Upload Plugin
# 3. Restart Jenkins
# 4. Test in real pipelines
```

## Changelog

Maintain a CHANGELOG.md in the jenkins-plugin directory:

```markdown
# Changelog

All notable changes to the Devlogs Jenkins Plugin will be documented in this file.

## [1.0.0] - 2026-01-12

### Added
- Initial release
- Pipeline step for streaming logs to devlogs
- Per-pipeline URL configuration
- Batch log processing
- Error resilient operation

### Known Issues
- None
```

## Support and Maintenance

After publishing:

1. **Monitor Issues**: Watch for GitHub issues and Jenkins JIRA tickets
2. **Security Updates**: Subscribe to Jenkins security advisories
3. **Dependency Updates**: Regularly update Jenkins parent POM version
4. **Compatibility**: Test with new Jenkins LTS releases

## Resources

- [Jenkins Plugin Tutorial](https://www.jenkins.io/doc/developer/tutorial/)
- [Plugin Hosting Guide](https://www.jenkins.io/doc/developer/publishing/)
- [Jenkins Plugin BOM](https://github.com/jenkinsci/bom)
- [Plugin Development Documentation](https://www.jenkins.io/doc/developer/)

## Troubleshooting

### Deploy Fails with 401 Unauthorized

- Check Maven credentials in `~/.m2/settings.xml`
- Verify Jenkins account permissions
- Ensure you're a member of the plugin's developer group

### Plugin Not Appearing in Update Center

- Wait 8-12 hours after deployment
- Check https://updates.jenkins.io/ for your plugin
- Verify the plugin was successfully deployed to repo.jenkins-ci.org

### Build Fails in CI

- Ensure Java 11 is used
- Check Maven version compatibility
- Verify all dependencies are available
