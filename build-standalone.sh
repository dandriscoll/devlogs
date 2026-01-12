#!/bin/bash
# Build standalone devlogs binary using PyInstaller
set -e

cd "$(dirname "$0")"

# Create entry point wrapper (imports will be resolved by PyInstaller)
cat > /tmp/devlogs_entry.py << 'EOF'
from devlogs.cli import app
if __name__ == "__main__":
    app()
EOF

# Install build dependencies
pip install pyinstaller

# Build the binary
pyinstaller \
    --onefile \
    --name devlogs-linux \
    --paths src \
    --hidden-import devlogs \
    --hidden-import devlogs.cli \
    --hidden-import devlogs.handler \
    --hidden-import devlogs.config \
    --hidden-import devlogs.context \
    --hidden-import devlogs.jenkins \
    --hidden-import devlogs.jenkins.cli \
    --hidden-import devlogs.jenkins.core \
    --hidden-import devlogs.opensearch \
    --hidden-import devlogs.opensearch.client \
    --hidden-import devlogs.opensearch.queries \
    --hidden-import typer \
    --hidden-import click \
    --collect-submodules devlogs \
    /tmp/devlogs_entry.py

# Binary is already named devlogs-linux via --name flag

echo "Binary created: dist/devlogs-linux"

# Run smoke tests
if [ -f "./test-standalone.sh" ]; then
    echo ""
    ./test-standalone.sh dist/devlogs-linux
fi

echo ""
echo "Upload to GitHub releases or host somewhere accessible to Jenkins"
