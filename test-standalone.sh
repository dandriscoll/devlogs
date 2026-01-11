#!/bin/bash
# Smoke tests for standalone devlogs binary
set -e

BINARY="${1:-dist/devlogs-linux}"

if [ ! -f "$BINARY" ]; then
    echo "ERROR: Binary not found: $BINARY"
    echo "Usage: $0 [path-to-binary]"
    exit 1
fi

echo "Testing binary: $BINARY"
echo "========================================"

# Test 1: Binary runs
echo -n "Test 1: Binary executes... "
"$BINARY" --help > /dev/null 2>&1
echo "PASS"

# Test 2: Shows version
echo -n "Test 2: Shows help output... "
"$BINARY" --help | grep -q "devlogs"
echo "PASS"

# Test 3: Jenkins subcommand exists
echo -n "Test 3: Jenkins subcommand... "
"$BINARY" jenkins --help > /dev/null 2>&1
echo "PASS"

# Test 4: Jenkins attach help
echo -n "Test 4: Jenkins attach help... "
"$BINARY" jenkins attach --help | grep -q "background"
echo "PASS"

# Test 5: Jenkins stop help
echo -n "Test 5: Jenkins stop help... "
"$BINARY" jenkins stop --help > /dev/null 2>&1
echo "PASS"

# Test 6: Init subcommand exists
echo -n "Test 6: Init subcommand... "
"$BINARY" init --help > /dev/null 2>&1
echo "PASS"

# Test 7: Diagnose subcommand exists
echo -n "Test 7: Diagnose subcommand... "
"$BINARY" diagnose --help > /dev/null 2>&1
echo "PASS"

echo "========================================"
echo "All smoke tests passed!"
