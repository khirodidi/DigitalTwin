# Installation Guide — Configuration Page + Persistent DB

## Files in this package

| File | Copy to | Action |
|---|---|---|
| `docker-compose.yml` | `docker-compose.yml` | **Replace** |
| `api/routes/config.py` | `api/routes/config.py` | **New file** |
| `api/main_patch.txt` | — | Instructions only (2-line edit) |
| `persistence/postgres_additions.py` | — | Instructions only (add 2 tables) |
| `frontend/src/App.jsx` | `frontend/src/App.jsx` | **Replace** |
| `frontend/src/pages/ConfigPage.jsx` | `frontend/src/pages/ConfigPage.jsx` | **New file** |
| `frontend/src/components/FactoryLayout.jsx` | `frontend/src/components/FactoryLayout.jsx` | **New file** |
| `frontend/src/components/SensorEditor.jsx` | `frontend/src/components/SensorEditor.jsx` | **New file** |
| `frontend/src/components/WorkerManager.jsx` | `frontend/src/components/WorkerManager.jsx` | **New file** |
| `frontend/src/components/TrajectoryMap.jsx` | `frontend/src/components/TrajectoryMap.jsx` | **New file** |

---

## Step 1 — Migrate existing database data (IMPORTANT)

If you already have data in the old named volume, copy it out **before** switching:

```bash
# Stop containers but keep the volume
docker compose down

# Create the local data directory
mkdir -p ./data/postgres

# Copy existing data out of the named volume into ./data/postgres
docker run --rm \
  -v digitaltwin_postgres_data:/from \
  -v "$(pwd)/data/postgres":/to \
  alpine sh -c "cd /from && cp -a . /to"

echo "Data migrated to ./data/postgres"
```

If you have no data worth keeping, skip this — the new folder is created automatically.

---

## Step 2 — Replace docker-compose.yml

The only change is the postgres volume line:

```yaml
# BEFORE
volumes:
  - postgres_data:/var/lib/postgresql/data

# AFTER
volumes:
  - ./data/postgres:/var/lib/postgresql/data
```

And `postgres_data:` is removed from the bottom `volumes:` block.

Your data now lives in `./data/postgres/` on your host machine. It survives
`docker compose down -v` and can be backed up with a simple `cp -r`.

---

## Step 3 — Add the two new tables

Open `persistence/postgres.py`. Find the `CREATE_TABLES` string and append
these two tables before the closing `"""`:

```sql
CREATE TABLE IF NOT EXISTS factory_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sensor_config (
    sensor_id     TEXT PRIMARY KEY REFERENCES sensors(sensor_id) ON DELETE CASCADE,
    coverage_type TEXT    NOT NULL DEFAULT 'passage',
    passable      BOOLEAN NOT NULL DEFAULT TRUE,
    description   TEXT             DEFAULT ''
);

INSERT INTO factory_config (key, value) VALUES
  ('factory_name',  'Factory A'),
  ('blueprint_url', ''),
  ('grid_cols',     '6'),
  ('grid_rows',     '5')
ON CONFLICT (key) DO NOTHING;
```

The tables are created automatically on next backend start (create_schema runs
at startup with `IF NOT EXISTS`).

---

## Step 4 — Register the config router

Open `api/main.py`, two small edits:

```python
# 1. Add 'config' to the import
from api.routes import assets, sensors, zones, events, system, config

# 2. Add one line after the other include_router calls
app.include_router(config.router, prefix="/api/config", tags=["Config"])
```

---

## Step 5 — Copy the frontend files

```bash
mkdir -p frontend/src/pages
cp ConfigPage.jsx      frontend/src/pages/
cp FactoryLayout.jsx   frontend/src/components/
cp SensorEditor.jsx    frontend/src/components/
cp WorkerManager.jsx   frontend/src/components/
cp TrajectoryMap.jsx   frontend/src/components/
cp App.jsx             frontend/src/
```

---

## Step 6 — Rebuild and start

```bash
docker compose up --build -d

# Seed if this is a fresh database
docker exec -i dt_postgres psql -U dt_user -d digital_twin < scripts/seed_db.sql

# Open the dashboard
open http://localhost:3000
```

Click the **⚙️ Configuration** button in the top-right of the header.

---

## New API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/config/factory` | Get factory name, blueprint, grid size |
| PUT | `/api/config/factory` | Update factory settings |
| GET | `/api/config/zones` | List zones with their sensors |
| POST | `/api/config/zones` | Create/update a zone + assign sensors |
| DELETE | `/api/config/zones/{id}` | Delete a zone |
| GET | `/api/config/sensors` | List sensors with coverage metadata |
| PUT | `/api/config/sensors/{id}` | Set coverage type + passable flag |
| GET | `/api/config/workers` | List all assets with authorisations |
| POST | `/api/config/workers` | Add a worker/forklift/pallet |
| PUT | `/api/config/workers/{id}` | Update name/type |
| DELETE | `/api/config/workers/{id}` | Delete asset + its authorisations |
| GET | `/api/config/workers/{id}/authorisations` | Get allowed zones + sensors |
| PUT | `/api/config/workers/{id}/authorisations` | Set allowed zones + sensors |
| GET | `/api/config/workers/{id}/trajectory?limit=N` | Location history for path drawing |

---

## Backing up your database

Because postgres data is now a plain folder:

```bash
# Backup
tar czf backup_$(date +%Y%m%d).tar.gz ./data/postgres

# Restore
docker compose down
rm -rf ./data/postgres
tar xzf backup_20260807.tar.gz
docker compose up -d
```
