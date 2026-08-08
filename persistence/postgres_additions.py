# =============================================================================
# persistence/postgres.py  — ADDITIONS ONLY
#
# Add the two new table definitions to the CREATE_TABLES string in the
# existing file, and add them to the create_schema() call.
#
# Find the CREATE_TABLES string in your existing postgres.py and append
# the two blocks below at the end (before the closing triple-quote).
# =============================================================================

# ── Append these two CREATE TABLE statements to CREATE_TABLES ─────────────────

NEW_TABLES = """
-- Stores factory-level config: blueprint image, grid size, factory name.
-- One row per key (key-value store).
CREATE TABLE IF NOT EXISTS factory_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Per-sensor metadata: what the sensor covers and whether workers can pass.
CREATE TABLE IF NOT EXISTS sensor_config (
    sensor_id     TEXT PRIMARY KEY REFERENCES sensors(sensor_id) ON DELETE CASCADE,
    coverage_type TEXT    NOT NULL DEFAULT 'passage',
    -- passage  : a corridor / walkway
    -- machine  : a machine workers operate next to
    -- storage  : shelving or rack area
    -- exit     : emergency exit / doorway
    passable      BOOLEAN NOT NULL DEFAULT TRUE,
    -- TRUE  : workers are expected to pass through (normal state)
    -- FALSE : workers should not normally be here (restricted area within zone)
    description   TEXT             DEFAULT ''
);
"""

# ── Seed default factory_config values if none exist ─────────────────────────

DEFAULT_CONFIG_SQL = """
INSERT INTO factory_config (key, value) VALUES
  ('factory_name',  'Factory A'),
  ('blueprint_url', ''),
  ('grid_cols',     '6'),
  ('grid_rows',     '5')
ON CONFLICT (key) DO NOTHING;
"""

# ── How to integrate into the existing create_schema() ───────────────────────
#
# In your existing create_schema() function, change:
#
#   def create_schema(dsn=None):
#       conn = get_conn(dsn)
#       with conn.cursor() as cur:
#           cur.execute(CREATE_TABLES)      # existing tables
#       conn.commit()
#
# To:
#
#   def create_schema(dsn=None):
#       conn = get_conn(dsn)
#       with conn.cursor() as cur:
#           cur.execute(CREATE_TABLES)      # existing tables
#           cur.execute(NEW_TABLES)         # new config tables
#           cur.execute(DEFAULT_CONFIG_SQL) # default values
#       conn.commit()
#
# OR simply paste the two SQL strings above into the existing CREATE_TABLES
# multi-line string — both approaches work identically.
# =============================================================================


# ── Complete drop-in replacement for create_schema() ─────────────────────────
# If you prefer, replace your entire create_schema() with this version:

def create_schema(dsn=None):
    """
    Create all tables. Safe to run multiple times (IF NOT EXISTS).
    Adds the two new config tables on top of the original schema.
    """
    import os, logging
    logger = logging.getLogger(__name__)

    conn = get_conn(dsn or os.getenv("POSTGRES_DSN", "postgresql://localhost/digital_twin"))
    with conn.cursor() as cur:
        # Original tables (unchanged)
        cur.execute(CREATE_TABLES)
        # New config tables
        cur.execute(NEW_TABLES)
        # Default factory config values
        cur.execute(DEFAULT_CONFIG_SQL)
    conn.commit()
    logger.info("Schema ready (including factory_config and sensor_config).")


# NOTE: CREATE_TABLES and get_conn() are defined earlier in the same file.
# This snippet only shows what to ADD / REPLACE — do not delete the rest
# of your existing postgres.py.
