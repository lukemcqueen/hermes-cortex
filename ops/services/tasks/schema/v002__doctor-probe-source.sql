-- ============================================================================
-- tasks schema v002 — admit doctor-probe source for the doctor's write-probe
-- (docs/design/task-workflow.md §8, L2 doctor).
--
-- The cortex doctor seeds a source='doctor-probe' row through task-db.py to
-- prove the LIVE write path (F-04 class: "valid JSON but dead table"), reads
-- it back, then completes+archives it via the normal lifecycle. The probe row
-- needs its own source value so it is distinguishable and prunable.
-- ============================================================================

ALTER TABLE tasks.tasks DROP CONSTRAINT IF EXISTS tasks_source_check;
ALTER TABLE tasks.tasks ADD CONSTRAINT tasks_source_check
    CHECK (source IN ('dream','session','manual','bridge','governance','inbox','doctor-probe'));
