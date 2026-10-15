-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- View Equipment Requirements as Technical Support Staff: a requirement marked
-- Unavailable needs a reason (Definition of Done 11b), shown to the Event
-- Coordinator. Unavailable is stored as the existing `rejected` value of
-- equipment_status; nothing is added to that enum, which Equipment
-- Reservations shares. The reason is only meaningful while the stored status
-- is `rejected`; it is cleared when the requirement goes back to Requested.
--
-- Requirements already marked Unavailable before this have no reason recorded
-- and keep a null one; they read as Unavailable with no reason shown.
--
-- Rollback: sql/down/026_requirement_unavailable_reason.sql

alter table public.coordinator_equipment_requirements
    add column if not exists unavailable_reason text;
