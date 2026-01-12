#!/bin/bash
# Test script for the Devlogs Jenkins Plugin

set -e

cd "$(dirname "$0")"

echo "=== Testing Devlogs Jenkins Plugin ==="
echo ""

# Check for Maven
if ! command -v mvn &> /dev/null; then
    echo "Error: Maven is not installed or not in PATH"
    exit 1
fi

echo "Running tests..."
mvn test

if [ $? -eq 0 ]; then
    echo ""
    echo "=== All Tests Passed ==="
else
    echo ""
    echo "=== Tests Failed ==="
    exit 1
fi
