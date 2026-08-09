-- =============================================================================
-- scripts/seed_db.sql
-- Seeds the digital_twin database with the factory layout and access rules.
--
-- Run with:
--   docker exec -i dt_postgres psql -U dt_user -d digital_twin < scripts/seed_db.sql
--
-- WHAT THIS FILE CONTROLS
-- ───────────────────────
-- 1. ZONES     — logical areas of the factory (Assembly, Warehouse, etc.)
-- 2. SENSORS   — which grid cell each sensor occupies and which zone it belongs to
-- 3. ASSETS    — workers and mobile objects that carry tags
-- 4. AUTHORISATIONS — which assets are allowed in which zones or sensors
--
-- Edit sections 1–4 to match your factory. The simulator and frontend
-- will automatically reflect whatever you put here.
-- =============================================================================

-- ─── Factory grid (blueprint must still be uploaded in the UI) ────────────────
INSERT INTO factory_config (key, value) VALUES
  ('factory_name', 'Factory A'),
  ('grid_cols',    '6'),
  ('grid_rows',    '5')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;

-- ─── Safety: re-run friendly ──────────────────────────────────────────────────
TRUNCATE authorisations, assets, sensors, zones RESTART IDENTITY CASCADE;


-- =============================================================================
-- SECTION 1 — ZONES
-- A zone is a named logical area that can span multiple sensor cells.
-- Workers are authorised at the zone level (coarser) or sensor level (finer).
--
-- Add/remove zones to match your floor plan.
-- zone_id must match what you use in SECTION 2 and SECTION 4.
-- =============================================================================
INSERT INTO zones (zone_id, name, description) VALUES
-- (zone_id,        display name,        description shown in dashboard)
  ('zone_A', 'Assembly',          'Main assembly area — general access'),
  ('zone_B', 'Warehouse',         'Raw materials storage'),
  ('zone_C', 'Control Room',      'Restricted — engineers only'),
  ('zone_D', 'Loading Bay',       'Forklift operating area'),
  ('zone_E', 'Finished Goods',    'Finished product storage');

-- Add more zones like this:
-- ('zone_F', 'Maintenance',  'Tool store and workshop');


-- =============================================================================
-- SECTION 2 — SENSORS
-- One sensor per grid cell. The grid is GRID_COLS × GRID_ROWS (default 6×5).
-- grid_row and grid_col are 0-based from the top-left corner.
-- The frontend renders sensors at position (grid_col, grid_row) on the map.
--
-- Sensor IDs must match what the simulator publishes (S01…S30 by default).
-- Formula: sensor_id = S + zero-padded( row * COLS + col + 1 )
--   e.g. row=0, col=0, cols=6 → S01
--        row=0, col=5, cols=6 → S06
--        row=1, col=0, cols=6 → S07
--
-- zone_id must match a zone from SECTION 1.
-- =============================================================================
INSERT INTO sensors (sensor_id, zone_id, grid_row, grid_col) VALUES
-- Zone A — Assembly (rows 0–1, cols 0–1)
  ('S01', 'zone_A', 0, 0),  ('S02', 'zone_A', 0, 1),
  ('S03', 'zone_A', 1, 0),  ('S04', 'zone_A', 1, 1),
-- Zone B — Warehouse (rows 0–1, cols 2–3)
  ('S05', 'zone_B', 0, 2),  ('S06', 'zone_B', 0, 3),
  ('S07', 'zone_B', 1, 2),  ('S08', 'zone_B', 1, 3),
-- Zone C — Control Room RESTRICTED (rows 0–1, cols 4–5)
  ('S09', 'zone_C', 0, 4),  ('S10', 'zone_C', 0, 5),
  ('S11', 'zone_C', 1, 4),  ('S12', 'zone_C', 1, 5),
-- Zone D — Loading Bay (rows 2–4, cols 0–2)
  ('S13', 'zone_D', 2, 0),  ('S14', 'zone_D', 2, 1),  ('S15', 'zone_D', 2, 2),
  ('S16', 'zone_D', 3, 0),  ('S17', 'zone_D', 3, 1),  ('S18', 'zone_D', 3, 2),
  ('S19', 'zone_D', 4, 0),  ('S20', 'zone_D', 4, 1),  ('S21', 'zone_D', 4, 2),
-- Zone E — Finished Goods (rows 2–4, cols 3–5)
  ('S22', 'zone_E', 2, 3),  ('S23', 'zone_E', 2, 4),  ('S24', 'zone_E', 2, 5),
  ('S25', 'zone_E', 3, 3),  ('S26', 'zone_E', 3, 4),  ('S27', 'zone_E', 3, 5),
  ('S28', 'zone_E', 4, 3),  ('S29', 'zone_E', 4, 4),  ('S30', 'zone_E', 4, 5);


-- =============================================================================
-- SECTION 3 — ASSETS (workers and mobile objects)
--
-- asset_id must match the IDs the simulator (or real tags) publish.
--   Default simulator: workers = W01…W05, forklifts = F01…F02, pallets = P01…P02
--   You can override counts with: --workers 3 --forklifts 1 --pallets 2
--
-- asset_type values:
--   'worker'   — human worker wearing a tag
--   'forklift' — motorised vehicle
--   'pallet'   — passive object on a pallet truck
--
-- Add a row here for every tag in your system.
-- If a tag publishes a location but has no row here, it still appears
-- on the map as asset_type='unknown' (auto-registered by the engine).
-- =============================================================================
INSERT INTO assets (asset_id, asset_type, name) VALUES
-- Workers
  ('W01', 'worker',   'Alice Martin'),
  ('W02', 'worker',   'Bob Chen'),
  ('W03', 'worker',   'Carlos Rivera'),   -- supervisor
  ('W04', 'worker',   'Diana Osei'),      -- supervisor
  ('W05', 'worker',   'Emir Yıldız'),     -- technician
-- Forklifts
  ('F01', 'forklift', 'Forklift 01'),
  ('F02', 'forklift', 'Forklift 02'),
-- Pallets
  ('P01', 'pallet',   'Pallet 01'),
  ('P02', 'pallet',   'Pallet 02');

-- To add more assets for a --workers 8 simulation:
-- ('W06', 'worker', 'Fatima Hassan'),
-- ('W07', 'worker', 'George Kim'),
-- ('W08', 'worker', 'Helen Novak'),


-- =============================================================================
-- SECTION 4 — AUTHORISATIONS
-- Defines which asset is allowed where.
--
-- Two levels of granularity:
--   allowed_type = 'zone'   → asset is authorised anywhere in that zone
--   allowed_type = 'sensor' → asset is only authorised at one specific cell
--
-- HOW THE ENGINE USES THIS:
--   When a tag is seen at sensor S07 (which is in zone_B):
--     1. Check if asset is authorised for sensor 'S07'  → AUTHORISED
--     2. Else check if asset is authorised for zone 'zone_B' → AUTHORISED
--     3. Else → VIOLATION  (red badge on dashboard)
--     4. If sensor S07 is OFFLINE → UNKNOWN  (amber badge, no false alert)
--
-- STRATEGY:
--   - Give most workers zone-level access (simpler to manage)
--   - Use sensor-level access for fine-grained restriction within a zone
--   - Leave a zone completely out of an asset's list to create a hard boundary
-- =============================================================================

-- ── W01 Alice: Assembly + Warehouse only (standard floor worker) ──────────────
INSERT INTO authorisations (asset_id, allowed_type, allowed_id) VALUES
  ('W01', 'zone', 'zone_A'),
  ('W01', 'zone', 'zone_B');

-- ── W02 Bob: Assembly + Loading Bay only ──────────────────────────────────────
INSERT INTO authorisations (asset_id, allowed_type, allowed_id) VALUES
  ('W02', 'zone', 'zone_A'),
  ('W02', 'zone', 'zone_D');

-- ── W03 Carlos (supervisor): all zones ────────────────────────────────────────
INSERT INTO authorisations (asset_id, allowed_type, allowed_id) VALUES
  ('W03', 'zone', 'zone_A'),
  ('W03', 'zone', 'zone_B'),
  ('W03', 'zone', 'zone_C'),
  ('W03', 'zone', 'zone_D'),
  ('W03', 'zone', 'zone_E');

-- ── W04 Diana (supervisor): all zones ─────────────────────────────────────────
INSERT INTO authorisations (asset_id, allowed_type, allowed_id) VALUES
  ('W04', 'zone', 'zone_A'),
  ('W04', 'zone', 'zone_B'),
  ('W04', 'zone', 'zone_C'),
  ('W04', 'zone', 'zone_D'),
  ('W04', 'zone', 'zone_E');

-- ── W05 Emir (technician): Control Room + Assembly only ───────────────────────
-- Also authorised at a specific sensor only within zone_B (e.g. the server
-- rack is at S05 — he can go there but not roam the rest of the warehouse)
INSERT INTO authorisations (asset_id, allowed_type, allowed_id) VALUES
  ('W05', 'zone',   'zone_C'),      -- full control room access
  ('W05', 'zone',   'zone_A'),      -- full assembly access
  ('W05', 'sensor', 'S05');         -- only one specific sensor in Warehouse

-- ── F01, F02 Forklifts: Loading Bay + Finished Goods (no office/warehouse) ────
INSERT INTO authorisations (asset_id, allowed_type, allowed_id) VALUES
  ('F01', 'zone', 'zone_D'),
  ('F01', 'zone', 'zone_E'),
  ('F02', 'zone', 'zone_D'),
  ('F02', 'zone', 'zone_E');

-- ── P01, P02 Pallets: track everywhere (passive — never a violation) ──────────
INSERT INTO authorisations (asset_id, allowed_type, allowed_id) VALUES
  ('P01', 'zone', 'zone_A'), ('P01', 'zone', 'zone_B'),
  ('P01', 'zone', 'zone_D'), ('P01', 'zone', 'zone_E'),
  ('P02', 'zone', 'zone_A'), ('P02', 'zone', 'zone_B'),
  ('P02', 'zone', 'zone_D'), ('P02', 'zone', 'zone_E');


-- =============================================================================
-- VERIFICATION — prints counts after seeding
-- =============================================================================
SELECT
  'Zones'          AS entity, COUNT(*) AS count FROM zones          UNION ALL
SELECT 'Sensors',              COUNT(*) FROM sensors                 UNION ALL
SELECT 'Assets',               COUNT(*) FROM assets                  UNION ALL
SELECT 'Authorisation rules',  COUNT(*) FROM authorisations;

-- Show each asset with their allowed zones/sensors
SELECT
  a.asset_id,
  a.asset_type,
  a.name,
  string_agg(
    CASE au.allowed_type
      WHEN 'zone'   THEN 'zone:' || au.allowed_id
      WHEN 'sensor' THEN 'sensor:' || au.allowed_id
    END,
    ', ' ORDER BY au.allowed_type, au.allowed_id
  ) AS authorised_for
FROM assets a
LEFT JOIN authorisations au USING (asset_id)
GROUP BY a.asset_id, a.asset_type, a.name
ORDER BY a.asset_type, a.asset_id;
