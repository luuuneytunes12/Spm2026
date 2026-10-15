-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- A tentative hold names the action the Event Coordinator must complete
-- before it expires (the hold is placed with an expiry AND an action). Null
-- on every booking that is not a hold, and on holds placed before this
-- migration; the API requires it for every new hold.
-- Rollback: sql/down/026_venue_hold_required_action.sql

alter table public.venue_bookings add column if not exists hold_action text;
