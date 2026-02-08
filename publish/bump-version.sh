#!/bin/bash
# Bump version across all package manifests (no git, no publish, just file edits)
set -e

cd "$(dirname "$0")/.."

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

if [[ $# -ne 2 ]]; then
    echo "Usage: $0 <old-version> <new-version>"
    echo "Example: $0 2.2.3 2.2.4"
    exit 1
fi

OLD="$1"
NEW="$2"

# Validate versions look like semver
if ! [[ "$OLD" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo -e "${RED}Invalid old version: $OLD${NC}"
    exit 1
fi
if ! [[ "$NEW" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo -e "${RED}Invalid new version: $NEW${NC}"
    exit 1
fi

update() {
    local file="$1" pattern="$2" replacement="$3"
    if [[ ! -f "$file" ]]; then
        echo -e "${RED}  MISSING  $file${NC}"
        return 1
    fi
    if grep -q "$pattern" "$file"; then
        sed -i "s|${pattern}|${replacement}|" "$file"
        echo -e "${GREEN}  updated  $file${NC}"
    else
        echo -e "${RED}  NOT FOUND  pattern in $file${NC}"
        return 1
    fi
}

echo "Bumping version: $OLD -> $NEW"
echo ""

update pyproject.toml \
    "version = \"${OLD}\"" \
    "version = \"${NEW}\""

update browser/package.json \
    "\"version\": \"${OLD}\"" \
    "\"version\": \"${NEW}\""

update dotnet/src/Devlogs/Devlogs.csproj \
    "<Version>${OLD}</Version>" \
    "<Version>${NEW}</Version>"

update go/devlogs.go \
    "const Version = \"${OLD}\"" \
    "const Version = \"${NEW}\""

update jenkins-plugin/pom.xml \
    "<version>${OLD}</version>" \
    "<version>${NEW}</version>"

# package-lock.json: replace both occurrences
if [[ -f browser/package-lock.json ]]; then
    sed -i "s|\"version\": \"${OLD}\"|\"version\": \"${NEW}\"|g" browser/package-lock.json
    echo -e "${GREEN}  updated  browser/package-lock.json${NC}"
fi

echo ""
echo -e "${GREEN}Done. All files updated to ${NEW}.${NC}"
