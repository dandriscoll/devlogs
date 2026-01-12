#!/bin/bash
# Publish devlogs-browser package to npm
set -e

cd "$(dirname "$0")/.."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Publishing devlogs-browser to npm ===${NC}"

# Check for required tools
if ! command -v npm &> /dev/null; then
    echo -e "${RED}Error: npm is required${NC}"
    exit 1
fi

cd browser

# Get version from package.json
VERSION=$(node -p "require('./package.json').version")
echo -e "Version: ${YELLOW}${VERSION}${NC}"

# Check if version already exists on npm
EXISTING=$(npm view devlogs-browser@${VERSION} version 2>/dev/null || echo "")
if [[ -n "$EXISTING" ]]; then
    echo -e "${YELLOW}Warning: Version ${VERSION} already exists on npm${NC}"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Install dependencies
echo "Installing dependencies..."
npm install

# Build the package
echo "Building package..."
npm run build

# Show what will be published
echo -e "\n${GREEN}Package contents:${NC}"
npm pack --dry-run 2>&1 | head -20

# Publish to npm
echo -e "\n${GREEN}Publishing to npm...${NC}"
if [[ "${DRY_RUN:-}" == "true" ]]; then
    echo -e "${YELLOW}DRY RUN: Would publish to npm${NC}"
    echo "npm publish"
else
    npm publish
fi

cd ..

echo -e "\n${GREEN}=== npm publish complete ===${NC}"
echo -e "Install with: ${YELLOW}npm install devlogs-browser@${VERSION}${NC}"
