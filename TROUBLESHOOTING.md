# Troubleshooting

## Blank page, console shows `main.<hash>.js  404 (Not Found)`

The page loaded an `index.html` that points at a JavaScript bundle which is not
on the server. The code is fine — something served a stale file.

**Fix, in order of likelihood:**

```bash
# 1. Hard-refresh the browser (drops the cached index.html)
#    Ctrl+Shift+R   ·   Cmd+Shift+R   ·   or use an incognito window

# 2. Clean rebuild
./scripts/rebuild.sh

# 3. Manual equivalent
docker compose down
docker rmi -f digitaltwin-frontend
rm -rf frontend/build
docker compose build --no-cache frontend
docker compose up -d
```

**Verify the container actually holds a bundle:**

```bash
docker exec dt_frontend ls /usr/share/nginx/html/static/js/
# expect: main.<hash>.js  (and a .map)

docker exec dt_frontend grep -o 'main\.[a-z0-9]*\.js' /usr/share/nginx/html/index.html
# the hash here MUST match the filename above
```

If they differ, the image contains a mismatched build — run `rebuild.sh`.
If the directory is empty, the React build failed; run
`docker compose build frontend` and read the output.

**Why it will not recur:** `nginx.conf` now sends
`Cache-Control: no-store` for `index.html` and `immutable` for hashed assets,
`.dockerignore` prevents a local `frontend/build/` being copied into the image,
and `Dockerfile.frontend` fails the build if no bundle is produced.

---

## Blank page with no 404

An unhandled render error. The app now wraps everything in an `ErrorBoundary`,
so you should see the message and component stack on screen instead. If you
still get a pure blank page, open DevTools → Console and read the first red
error.

---

## Sensors all show OFFLINE / no temperature or humidity

The engine now registers unknown sensors automatically and treats database
writes as best-effort, so this should be resolved. To confirm data is flowing:

```bash
docker logs dt_backend --tail 50          # look for "DB write failed"
docker exec dt_backend python -c "
from persistence.postgres import get_conn
c=get_conn()
with c.cursor() as cur:
    cur.execute('SELECT COUNT(*) FROM env_readings'); print('env_readings:', cur.fetchone()[0])
    cur.execute('SELECT COUNT(*) FROM sensors');      print('sensors:',      cur.fetchone()[0])
"

# Watch raw MQTT traffic
docker exec dt_mosquitto mosquitto_sub -t 'wsn/#' -C 10
```

If MQTT is silent, the simulator is not running:
`docker compose --profile sim up simulator`

---

## Blueprint upload hangs

Click **Diagnose** on the upload panel — it reports the storage directory,
whether it is writable, and the size limit. Common causes:

| Cause | Fix |
|---|---|
| File over 25 MB | nginx rejects it; use a smaller image |
| Backend unreachable | check `REACT_APP_API_URL` and that `dt_backend` is up |
| Directory not writable | `docker volume rm digitaltwin_blueprint_store` then restart |

---

## Setup screen keeps reappearing

Grid size **and** a blueprint image are both mandatory. Check:

```bash
curl http://localhost:8000/api/config/factory
# configured must be true
```

---

## Everything shows CRITICAL with many access violations

Assets with no authorisations violate on every position. Open
**Configuration → Workers** and use **Authorise all assets for all zones**,
or:

```bash
curl -X POST http://localhost:8000/api/config/workers/bulk-authorise \
  -H "Content-Type: application/json" \
  -d '{"asset_ids":"all","allowed_zones":["zone_A","zone_B"],"mode":"replace"}'
```

---

## Frontend image fails to build

Docker reports only `exit code: 1`. To see the real compiler error:

```bash
./scripts/diagnose-build.sh
```

This runs the build in a throwaway container and prints the full output —
`Failed to compile` is followed by the exact file and line.

**Known causes and their fixes (all already applied):**

| Cause | Fix in `Dockerfile.frontend` |
|---|---|
| Docker sets `CI=true`, so CRA turns ESLint *warnings* into errors | `ENV CI=false` |
| Lint errors (unused var, hook order) break the deploy build | `ENV DISABLE_ESLINT_PLUGIN=true` |
| `npm run build \| tee` returns tee's exit code, masking failure | pipe removed |
| Webpack heap exhaustion on larger trees | `NODE_OPTIONS=--max-old-space-size=4096` |

**If the assertion at step 7 fails** (`test -f build/index.html`), the build
itself failed but its exit code was swallowed. The Dockerfile no longer pipes,
so the compiler error now appears directly in the Docker output.
