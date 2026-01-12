#!/bin/bash
# Master release script - syncs versions and publishes to all platforms
set -e

cd "$(dirname "$0")/.."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

usage() {
    cat <<EOF
Usage: $0 [OPTIONS] [VERSION]

Publish devlogs to PyPI, npm, and GitHub.

Arguments:
  VERSION         New version number (e.g., 1.2.0). If not provided, uses current version.

Options:
  --bump-patch    Bump patch version (1.0.0 -> 1.0.1)
  --bump-minor    Bump minor version (1.0.0 -> 1.1.0)
  --bump-major    Bump major version (1.0.0 -> 2.0.0)
  --pypi-only     Only publish to PyPI
  --npm-only      Only publish to npm
  --github-only   Only create GitHub release
  --dry-run       Show what would be done without making changes
  --skip-tests    Skip running tests before release
  --help          Show this help message

Examples:
  $0                      # Release current version to all platforms
  $0 1.2.0                # Set version to 1.2.0 and release
  $0 --bump-patch         # Bump patch version and release
  $0 --dry-run            # Preview release without making changes
  $0 --pypi-only          # Only publish to PyPI
EOF
    exit 0
}

# Parse arguments
BUMP=""
PYPI=true
NPM=true
GITHUB=true
DRY_RUN=""
SKIP_TESTS=false
NEW_VERSION=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --bump-patch) BUMP="patch"; shift ;;
        --bump-minor) BUMP="minor"; shift ;;
        --bump-major) BUMP="major"; shift ;;
        --pypi-only) NPM=false; GITHUB=false; shift ;;
        --npm-only) PYPI=false; GITHUB=false; shift ;;
        --github-only) PYPI=false; NPM=false; shift ;;
        --dry-run) DRY_RUN="true"; shift ;;
        --skip-tests) SKIP_TESTS=true; shift ;;
        --help) usage ;;
        -*) echo -e "${RED}Unknown option: $1${NC}"; usage ;;
        *) NEW_VERSION="$1"; shift ;;
    esac
done

# Get current version
CURRENT_VERSION=$(grep -oP 'version = "\K[^"]+' pyproject.toml)
echo -e "${BLUE}Current version: ${CURRENT_VERSION}${NC}"

# Calculate new version if bumping
if [[ -n "$BUMP" ]]; then
    IFS='.' read -ra PARTS <<< "$CURRENT_VERSION"
    MAJOR=${PARTS[0]}
    MINOR=${PARTS[1]}
    PATCH=${PARTS[2]}

    case $BUMP in
        patch) PATCH=$((PATCH + 1)) ;;
        minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
        major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
    esac

    NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"
fi

# Use new version or current version
VERSION="${NEW_VERSION:-$CURRENT_VERSION}"
echo -e "${GREEN}Release version: ${VERSION}${NC}"

if [[ "$VERSION" != "$CURRENT_VERSION" ]]; then
    echo -e "${YELLOW}Version will be updated: ${CURRENT_VERSION} -> ${VERSION}${NC}"
fi

# Confirmation
echo ""
echo "Will publish to:"
[[ "$PYPI" == "true" ]] && echo "  - PyPI (pip install devlogs)"
[[ "$NPM" == "true" ]] && echo "  - npm (npm install devlogs-browser)"
[[ "$GITHUB" == "true" ]] && echo "  - GitHub Releases (standalone binary)"

if [[ "$DRY_RUN" == "true" ]]; then
    echo -e "\n${YELLOW}DRY RUN MODE - no changes will be made${NC}"
fi

echo ""
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

# Update version in files if changed
if [[ "$VERSION" != "$CURRENT_VERSION" && "$DRY_RUN" != "true" ]]; then
    echo -e "\n${GREEN}Updating version to ${VERSION}...${NC}"

    # Update pyproject.toml
    sed -i "s/version = \"${CURRENT_VERSION}\"/version = \"${VERSION}\"/" pyproject.toml
    echo "  Updated pyproject.toml"

    # Update browser/package.json
    sed -i "s/\"version\": \"${CURRENT_VERSION}\"/\"version\": \"${VERSION}\"/" browser/package.json
    echo "  Updated browser/package.json"

    # Commit version bump
    git add pyproject.toml browser/package.json
    git commit -m "Bump version to ${VERSION}"
    echo "  Committed version bump"
fi

# Run tests
if [[ "$SKIP_TESTS" != "true" && "$DRY_RUN" != "true" ]]; then
    echo -e "\n${GREEN}Running tests...${NC}"
    source .venv/bin/activate 2>/dev/null || true
    if python3 -m pytest tests/ -q; then
        echo -e "${GREEN}Tests passed${NC}"
    else
        echo -e "${RED}Tests failed! Aborting release.${NC}"
        exit 1
    fi
fi

# Build standalone binary (needed for GitHub release)
if [[ "$GITHUB" == "true" && "$DRY_RUN" != "true" ]]; then
    echo -e "\n${GREEN}Building standalone binary...${NC}"
    ./build-standalone.sh
fi

# Export DRY_RUN for child scripts
export DRY_RUN

# Publish to PyPI
if [[ "$PYPI" == "true" ]]; then
    echo -e "\n${BLUE}========================================${NC}"
    ./publish-pypi.sh
fi

# Publish to npm
if [[ "$NPM" == "true" ]]; then
    echo -e "\n${BLUE}========================================${NC}"
    ./publish-npm.sh
fi

# Create GitHub release
if [[ "$GITHUB" == "true" ]]; then
    echo -e "\n${BLUE}========================================${NC}"
    ./publish-github.sh
fi

# Summary
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}=== Release ${VERSION} Complete ===${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
[[ "$PYPI" == "true" ]] && echo -e "PyPI:   ${YELLOW}pip install devlogs==${VERSION}${NC}"
[[ "$NPM" == "true" ]] && echo -e "npm:    ${YELLOW}npm install devlogs-browser@${VERSION}${NC}"
[[ "$GITHUB" == "true" ]] && echo -e "GitHub: ${YELLOW}https://github.com/dandriscoll/devlogs/releases/tag/v${VERSION}${NC}"
