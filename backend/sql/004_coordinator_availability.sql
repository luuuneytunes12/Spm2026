-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Supports the "Mark myself unavailable" story (Event Coordinator):
--
--   As an Event Coordinator, I want to mark myself as unavailable, so that
--   my assigned events are automatically reassigned to another coordinator.
--
-- Adds the column a Coordinator toggles to say "don't route new (or
-- reassigned) events to me right now". `users` is a single shared table
-- across every role -- every row gets the column -- but only Coordinators
-- are ever read or written through it; every other role's value just sits
-- at the default and is ignored.

alter table public.users add column if not exists is_available boolean not null default true;

-- Verify:
select id, name, role, is_available from public.users order by id;
