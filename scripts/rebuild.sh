#!/usr/bin/env bash
# =============================================================================
# scripts/rebuild.sh — clean rebuild that eliminates stale-bundle 404s
#
# Symptom this fixes:
#   Blank page + console error like
#     main.0d9efe30.js:1  Failed to load resource: 404 (Not Found)
#
# Cause:
#   The browser (or nginx, or the Docker layer cache) is serving an old
#   index.html that references a bundle hash which no longer exists after a
#   rebuild. Nothing is wrong with the code.
# =============================================================================
set -e

echo "──────────────────────────────────────────────────────────"
echo "  Clean frontend rebuild"
echo "──────────────────────────────────────────────────────────"

echo "[1/5] Stopping containers (database is preserved)…"
docker compose down

echo "[2/5] Removing the frontend image and any stale build output…"
docker rmi -f digitaltwin-frontend 2>/dev/null || true
rm -rf frontend/build

echo "[3/5] Rebuilding the frontend with no cache…"
docker compose build --no-cache frontend

echo "[4/5] Starting the stack…"
docker compose up -d

echo "[5/5] Verifying the bundle is present in the container…"
sleep 4
if docker exec dt_frontend ls /usr/share/nginx/html/static/js/ 2>/dev/null | grep -q '\.js$'; then
    echo "      ✓ Bundle found:"
    docker exec dt_frontend ls /usr/share/nginx/html/static/js/ | sed 's/^/        /'
    echo "      ✓ index.html references:"
    docker exec dt_frontend grep -o 'main\.[a-z0-9]*\.js' /usr/share/nginx/html/index.html \
        | sort -u | sed 's/^/        /'
else
    echo "      ✗ No bundle in the container — the build failed."
    echo "        Inspect it with:  docker compose build frontend"
    exit 1
fi

echo ""
echo "──────────────────────────────────────────────────────────"
echo "  Done.  Open http://localhost:3000"
echo ""
echo "  IMPORTANT: hard-refresh your browser to drop the cached"
echo "  index.html that caused the 404:"
echo "     Linux / Windows : Ctrl + Shift + R"
echo "     macOS           : Cmd + Shift + R"
echo "  Or open the site in a private/incognito window."
echo "──────────────────────────────────────────────────────────"
