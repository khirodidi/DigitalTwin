-- =============================================================================
-- scripts/seed_db.sql
-- Seeds the digital_twin database with the factory layout defined in
-- frontend/src/config/factory.js
--
-- Run with:
--   psql postgresql://dt_user:dt_pass@localhost/digital_twin -f scripts/seed_db.sql
-- Or inside Docker:
--   docker exec -i dt_postgres psql -U dt_user -d digital_twin < scripts/seed_db.sql
-- =============================================================================

-- ─── Zones ───────────────────────────────────────────────────────────────────
INSERT INTO zones (zone_id, name, description) VALUES
  ('zone_A', 'Zone A', 'Assembly area'),
  ('zone_B', 'Zone B', 'Warehouse — raw materials'),
  ('zone_C', 'Zone C', 'Control room — restricted'),
  ('zone_D', 'Zone D', 'Loading bay'),
  ('zone_E', 'Zone E', 'Finished goods storage')
ON CONFLICT (zone_id) DO NOTHING;

-- ─── Sensors (30 sensors across 6×5 grid) ────────────────────────────────────
INSERT INTO sensors (sensor_id, zone_id, grid_row, grid_col) VALUES
  -- Zone A (rows 0-1, cols 0-1)
  ('S01', 'zone_A', 0, 0), ('S02', 'zone_A', 0, 1),
  ('S03', 'zone_A', 1, 0), ('S04', 'zone_A', 1, 1),
  -- Zone B (rows 0-1, cols 2-3)
  ('S05', 'zone_B', 0, 2), ('S06', 'zone_B', 0, 3),
  ('S07', 'zone_B', 1, 2), ('S08', 'zone_B', 1, 3),
  -- Zone C (rows 0-1, cols 4-5)
  ('S09', 'zone_C', 0, 4), ('S10', 'zone_C', 0, 5),
  ('S11', 'zone_C', 1, 4), ('S12', 'zone_C', 1, 5),
  -- Zone D (rows 2-4, cols 0-2)
  ('S13', 'zone_D', 2, 0), ('S14', 'zone_D', 2, 1), ('S15', 'zone_D', 2, 2),
  ('S16', 'zone_D', 3, 0), ('S17', 'zone_D', 3, 1), ('S18', 'zone_D', 3, 2),
  ('S19', 'zone_D', 4, 0), ('S20', 'zone_D', 4, 1), ('S21', 'zone_D', 4, 2),
  -- Zone E (rows 2-4, cols 3-5)
  ('S22', 'zone_E', 2, 3), ('S23', 'zone_E', 2, 4), ('S24', 'zone_E', 2, 5),
  ('S25', 'zone_E', 3, 3), ('S26', 'zone_E', 3, 4), ('S27', 'zone_E', 3, 5),
  ('S28', 'zone_E', 4, 3), ('S29', 'zone_E', 4, 4), ('S30', 'zone_E', 4, 5)
ON CONFLICT (sensor_id) DO NOTHING;

-- ─── Sample assets ────────────────────────────────────────────────────────────
INSERT INTO assets (asset_id, asset_type, name) VALUES
  ('W01', 'worker', 'Worker 01'),
  ('W02', 'worker', 'Worker 02'),
  ('W03', 'worker', 'Worker 03'),
  ('W04', 'worker', 'Worker 04'),
  ('W05', 'worker', 'Worker 05'),
  ('F01', 'object', 'Forklift 01'),
  ('F02', 'object', 'Forklift 02'),
  ('P01', 'object', 'Pallet 01'),
  ('P02', 'object', 'Pallet 02')
ON CONFLICT (asset_id) DO NOTHING;

-- ─── Authorisations ───────────────────────────────────────────────────────────
-- W01, W02: authorised for zones A and B (general workers)
INSERT INTO authorisations (asset_id, allowed_type, allowed_id) VALUES
  ('W01', 'zone', 'zone_A'), ('W01', 'zone', 'zone_B'),
  ('W02', 'zone', 'zone_A'), ('W02', 'zone', 'zone_B')
ON CONFLICT DO NOTHING;

-- W03, W04: authorised everywhere (supervisors)
INSERT INTO authorisations (asset_id, allowed_type, allowed_id) VALUES
  ('W03', 'zone', 'zone_A'), ('W03', 'zone', 'zone_B'),
  ('W03', 'zone', 'zone_C'), ('W03', 'zone', 'zone_D'), ('W03', 'zone', 'zone_E'),
  ('W04', 'zone', 'zone_A'), ('W04', 'zone', 'zone_B'),
  ('W04', 'zone', 'zone_C'), ('W04', 'zone', 'zone_D'), ('W04', 'zone', 'zone_E')
ON CONFLICT DO NOTHING;

-- W05: authorised for zone C only (control room technician)
INSERT INTO authorisations (asset_id, allowed_type, allowed_id) VALUES
  ('W05', 'zone', 'zone_C'), ('W05', 'zone', 'zone_B')
ON CONFLICT DO NOTHING;

-- Forklifts: authorised for zones D and E (loading/storage areas)
INSERT INTO authorisations (asset_id, allowed_type, allowed_id) VALUES
  ('F01', 'zone', 'zone_D'), ('F01', 'zone', 'zone_E'),
  ('F02', 'zone', 'zone_D'), ('F02', 'zone', 'zone_E')
ON CONFLICT DO NOTHING;

-- Pallets: authorised everywhere (passive objects, track only)
INSERT INTO authorisations (asset_id, allowed_type, allowed_id) VALUES
  ('P01', 'zone', 'zone_A'), ('P01', 'zone', 'zone_B'), ('P01', 'zone', 'zone_D'), ('P01', 'zone', 'zone_E'),
  ('P02', 'zone', 'zone_A'), ('P02', 'zone', 'zone_B'), ('P02', 'zone', 'zone_D'), ('P02', 'zone', 'zone_E')
ON CONFLICT DO NOTHING;

-- ─── Verify ───────────────────────────────────────────────────────────────────
SELECT 'Zones:'   AS entity, COUNT(*) FROM zones    UNION ALL
SELECT 'Sensors:', COUNT(*) FROM sensors             UNION ALL
SELECT 'Assets:',  COUNT(*) FROM assets              UNION ALL
SELECT 'Auth:',    COUNT(*) FROM authorisations;
