#!/bin/bash
# Create GitHub release with standalone binary
set -e

cd "$(dirname "$0")/.."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Creating GitHub Release ===${NC}"

# Check for required tools
if ! command -v gh &> /dev/null; then
    echo -e "${RED}Error: GitHub CLI (gh) is required${NC}"
    echo "Install: https://cli.github.com/"
    exit 1
fi

# Check gh authentication
if ! gh auth status &> /dev/null; then
    echo -e "${RED}Error: Not authenticated with GitHub CLI${NC}"
    echo "Run: gh auth login"
    exit 1
fi

# Get version from pyproject.toml (source of truth)
VERSION=$(grep -oP 'version = "\K[^"]+' pyproject.toml)
TAG="v${VERSION}"
echo -e "Version: ${YELLOW}${VERSION}${NC}"
echo -e "Tag: ${YELLOW}${TAG}${NC}"

# Check if binary exists
BINARY="dist/devlogs-linux"
if [[ ! -f "$BINARY" ]]; then
    echo -e "${YELLOW}Binary not found. Building...${NC}"
    ./build-standalone.sh
fi

# Verify binary works
echo "Verifying binary..."
if ! "${BINARY}" --help &> /dev/null; then
    echo -e "${RED}Error: Binary verification failed${NC}"
    exit 1
fi
echo -e "${GREEN}Binary OK${NC}"

# Check if tag already exists
if git rev-parse "$TAG" &> /dev/null; then
    echo -e "${YELLOW}Warning: Tag ${TAG} already exists${NC}"
    read -p "Delete and recreate? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git tag -d "$TAG" 2>/dev/null || true
        git push origin --delete "$TAG" 2>/dev/null || true
    else
        exit 1
    fi
fi

# Check if release already exists
if gh release view "$TAG" &> /dev/null; then
    echo -e "${YELLOW}Warning: Release ${TAG} already exists${NC}"
    read -p "Delete and recreate? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        gh release delete "$TAG" --yes
    else
        exit 1
    fi
fi

# Generate release notes
RELEASE_NOTES=$(cat <<EOF
## Devlogs ${VERSION}

### Installation

**Python (pip):**
\`\`\`bash
pip install devlogs==${VERSION}
\`\`\`

**Browser (npm):**
\`\`\`bash
npm install devlogs-browser@${VERSION}
\`\`\`

**Standalone binary:**
Download \`devlogs-linux\` below (no Python required).

### Changes

See [CHANGELOG.md](CHANGELOG.md) or commit history for details.

### Standalone Binary Usage

\`\`\`bash
# Download and make executable
curl -sL https://github.com/dandriscoll/devlogs/releases/download/${TAG}/devlogs-linux -o devlogs
chmod +x devlogs

# Use with --url flag
./devlogs --url 'https://user:pass@host:9200/index' tail
\`\`\`
EOF
)

echo -e "\n${GREEN}Release notes:${NC}"
echo "$RELEASE_NOTES"

# Create release
echo -e "\n${GREEN}Creating GitHub release...${NC}"
if [[ "${DRY_RUN:-}" == "true" ]]; then
    echo -e "${YELLOW}DRY RUN: Would create release ${TAG}${NC}"
    echo "gh release create ${TAG} ${BINARY} --title \"Devlogs ${VERSION}\" --notes \"...\""
else
    # Create tag
    git tag -a "$TAG" -m "Release ${VERSION}"
    git push origin "$TAG"

    # Create release with binary
    gh release create "$TAG" \
        "$BINARY" \
        --title "Devlogs ${VERSION}" \
        --notes "$RELEASE_NOTES"
fi

echo -e "\n${GREEN}=== GitHub release complete ===${NC}"
echo -e "Release URL: ${YELLOW}https://github.com/dandriscoll/devlogs/releases/tag/${TAG}${NC}"
