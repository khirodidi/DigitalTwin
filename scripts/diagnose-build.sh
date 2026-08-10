#!/usr/bin/env bash
# =============================================================================
# scripts/diagnose-build.sh
# Shows the ACTUAL React build error, which Docker hides behind "exit code: 1".
# =============================================================================
cd "$(dirname "$0")/.."

echo "════════════════════════════════════════════════════════"
echo "  Frontend build diagnostics"
echo "════════════════════════════════════════════════════════"
echo ""
echo "Running the build inside a throwaway container so you see"
echo "the full compiler output..."
echo ""

docker run --rm -v "$(pwd)/frontend":/app -w /app node:20-alpine sh -c '
  echo "── npm install ──"
  npm install --no-audit --no-fund 2>&1 | tail -15
  echo ""
  echo "── react-scripts build (full output) ──"
  CI=false DISABLE_ESLINT_PLUGIN=true npm run build
  echo ""
  echo "── exit code: $? ──"
  echo "── build output ──"
  ls -la build 2>/dev/null || echo "(no build directory created)"
  ls -la build/static/js 2>/dev/null || true
'

echo ""
echo "════════════════════════════════════════════════════════"
echo "  If you see 'Failed to compile' above, the file and line"
echo "  are named directly beneath it."
echo "════════════════════════════════════════════════════════"
