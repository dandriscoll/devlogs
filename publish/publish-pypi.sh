#!/bin/bash
# Publish devlogs Python package to PyPI
set -e

cd "$(dirname "$0")/.."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Publishing devlogs to PyPI ===${NC}"

# Check for required tools
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is required${NC}"
    exit 1
fi

# Get version from pyproject.toml
VERSION=$(grep -oP 'version = "\K[^"]+' pyproject.toml)
echo -e "Version: ${YELLOW}${VERSION}${NC}"

# Check if version already exists on PyPI
if pip index versions devlogs 2>/dev/null | grep -q "$VERSION"; then
    echo -e "${YELLOW}Warning: Version ${VERSION} may already exist on PyPI${NC}"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Ensure build tools are installed
echo "Installing/upgrading build tools..."
pip install --upgrade build twine

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf dist/*.tar.gz dist/*.whl build/*.egg-info 2>/dev/null || true

# Build the package
echo "Building package..."
python3 -m build

# Show what will be uploaded
echo -e "\n${GREEN}Built packages:${NC}"
ls -la dist/*.tar.gz dist/*.whl 2>/dev/null

# Upload to PyPI
echo -e "\n${GREEN}Uploading to PyPI...${NC}"
if [[ "${DRY_RUN:-}" == "true" ]]; then
    echo -e "${YELLOW}DRY RUN: Would upload to PyPI${NC}"
    echo "twine upload dist/devlogs-${VERSION}*"
else
    # Use TestPyPI if specified
    if [[ "${TEST_PYPI:-}" == "true" ]]; then
        echo "Uploading to TestPyPI..."
        twine upload --repository testpypi dist/devlogs-${VERSION}*
    else
        twine upload dist/devlogs-${VERSION}*
    fi
fi

echo -e "\n${GREEN}=== PyPI publish complete ===${NC}"
echo -e "Install with: ${YELLOW}pip install devlogs==${VERSION}${NC}"
