#!/bin/bash
# Publish both devlogs-browser and devlogs-node packages to npm
set -e

DIR="$(dirname "$0")"

"$DIR/publish-browser.sh"
"$DIR/publish-node.sh"
