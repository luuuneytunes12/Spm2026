-- Event Coordinator Lead role. Safe to re-run (idempotent).
-- The label is already present on the live database; this is for fresh ones.
-- ADD VALUE cannot run inside a transaction block on older postgres, and the
-- new label is not usable until it commits -- run the two statements apart.

alter type user_role add value if not exists 'event_coordinator_lead';

-- Then (separately):
-- update public.users set role = 'event_coordinator_lead'
--   where email = 'event_coord_lead@cs.local';
