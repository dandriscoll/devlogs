#!/bin/bash
# Build script for the Devlogs Jenkins Plugin

set -e

cd "$(dirname "$0")"

echo "=== Building Devlogs Jenkins Plugin ==="
echo ""

# Check for Maven
if ! command -v mvn &> /dev/null; then
    echo "Error: Maven is not installed or not in PATH"
    echo "Please install Maven: https://maven.apache.org/install.html"
    exit 1
fi

# Check for Java
if ! command -v java &> /dev/null; then
    echo "Error: Java is not installed or not in PATH"
    echo "Please install Java 11 or higher"
    exit 1
fi

echo "Maven version:"
mvn --version
echo ""

# Build the plugin
echo "Building plugin..."
mvn clean package -DskipTests

if [ $? -eq 0 ]; then
    echo ""
    echo "=== Build Successful ==="
    echo ""
    echo "Plugin file: target/devlogs.hpi"
    echo ""
    echo "To install:"
    echo "1. Go to Jenkins > Manage Jenkins > Manage Plugins > Advanced"
    echo "2. Under 'Upload Plugin', choose target/devlogs.hpi"
    echo "3. Click 'Upload' and restart Jenkins"
    echo ""
    echo "Or run locally for testing:"
    echo "  mvn hpi:run"
    echo "  Then visit http://localhost:8080/jenkins"
else
    echo ""
    echo "=== Build Failed ==="
    exit 1
fi
