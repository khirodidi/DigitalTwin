#!/usr/bin/env bash
# =============================================================================
# scripts/build-frontend.sh
# Builds the React app OUTSIDE Docker so compile errors are readable.
#
# Docker hides CRA's error output behind "exit code: 1". Run this first when
# the frontend image fails to build.
# =============================================================================
set -e
cd "$(dirname "$0")/../frontend"

echo "── Installing dependencies ──"
npm install

echo ""
echo "── Building (CI=false so warnings do not fail the build) ──"
CI=false npm run build

echo ""
echo "── Result ──"
if [ -f build/index.html ]; then
    echo "  ✓ build/index.html created"
    ls -la build/static/js/*.js | sed 's/^/    /'
    echo "  ✓ Frontend compiles — the Docker build should now succeed"
else
    echo "  ✗ No build output produced"
    exit 1
fi
