# Releasing Devlogs

Guide for publishing devlogs to PyPI, npm, and GitHub Releases.

## Prerequisites

### For PyPI

```bash
pip install build twine
```

You'll need PyPI credentials configured:
- Create account at https://pypi.org/
- Generate API token at https://pypi.org/manage/account/token/
- Configure `~/.pypirc` or use `TWINE_USERNAME` and `TWINE_PASSWORD` env vars

### For npm

```bash
npm login
```

You'll need an npm account at https://www.npmjs.com/

### For GitHub Releases

```bash
# Install GitHub CLI
# macOS: brew install gh
# Linux: https://github.com/cli/cli/blob/trunk/docs/install_linux.md

# Authenticate
gh auth login
```

## Quick Release

The easiest way to release is using the master script (from project root):

```bash
# Release current version to all platforms
./publish/release.sh

# Bump patch version (1.0.0 -> 1.0.1) and release
./publish/release.sh --bump-patch

# Bump minor version (1.0.0 -> 1.1.0) and release
./publish/release.sh --bump-minor

# Set specific version and release
./publish/release.sh 1.2.0

# Preview without making changes
./publish/release.sh --dry-run
```

## Individual Scripts

All scripts can be run from the project root.

### PyPI Only

```bash
./publish/publish-pypi.sh

# Test with TestPyPI first
TEST_PYPI=true ./publish/publish-pypi.sh

# Dry run
DRY_RUN=true ./publish/publish-pypi.sh
```

### npm Only

```bash
./publish/publish-npm.sh

# Dry run
DRY_RUN=true ./publish/publish-npm.sh
```

### GitHub Release Only

```bash
./publish/publish-github.sh

# Dry run
DRY_RUN=true ./publish/publish-github.sh
```

## Version Management

Versions are kept in sync across:
- `pyproject.toml` (Python package) - **source of truth**
- `browser/package.json` (npm package)

The `release.sh` script automatically syncs these when bumping versions.

### Manual Version Update

If you need to update versions manually:

```bash
# Edit pyproject.toml
sed -i 's/version = "1.0.0"/version = "1.1.0"/' pyproject.toml

# Edit browser/package.json
sed -i 's/"version": "1.0.0"/"version": "1.1.0"/' browser/package.json

# Commit
git add pyproject.toml browser/package.json
git commit -m "Bump version to 1.1.0"
```

## Release Checklist

Before releasing:

1. **Run tests**
   ```bash
   pytest tests/
   ```

2. **Update documentation** if needed
   - README.md
   - HOWTO-CLI.md
   - Other docs

3. **Check git status**
   ```bash
   git status  # Should be clean
   ```

4. **Verify current version**
   ```bash
   grep version pyproject.toml
   grep version browser/package.json
   ```

## Standalone Binary

The standalone binary is built automatically during GitHub release. To build manually:

```bash
./build-standalone.sh
# Output: dist/devlogs-linux
```

The binary is self-contained and doesn't require Python.

## Troubleshooting

### PyPI Upload Fails

```bash
# Check credentials
cat ~/.pypirc

# Or use environment variables
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-xxxxxxxxx
```

### npm Publish Fails

```bash
# Check login status
npm whoami

# Re-login if needed
npm login
```

### GitHub Release Fails

```bash
# Check authentication
gh auth status

# Re-authenticate
gh auth login
```

### Version Already Exists

If a version already exists on PyPI/npm:
- You cannot overwrite existing versions
- Bump to a new version number
- Or use `--bump-patch` to auto-increment

### Binary Build Fails

```bash
# Ensure PyInstaller is installed
pip install pyinstaller

# Try building manually
./build-standalone.sh
```

## CI/CD Integration

For automated releases, set these secrets in your CI environment:

```yaml
# GitHub Actions example
env:
  TWINE_USERNAME: __token__
  TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN }}
  NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
```

Then in your workflow:

```yaml
- name: Release
  run: |
    npm config set //registry.npmjs.org/:_authToken=$NPM_TOKEN
    ./release.sh --bump-patch
```
