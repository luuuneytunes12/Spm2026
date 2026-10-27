-- From backend/sql/033_venue_booking_released.sql. Safe to re-run: staging had part of this
-- applied by hand before the pipeline existed.

-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Venue Bookings of an Event that is cancelled or completed become
-- 'released' (kept as history, the venue free again), and the Activity Log
-- records that with the System as the actor: changed_by is null.
-- Rollback: sql/down/033_venue_booking_released.sql

alter type public.booking_status add value if not exists 'released';

alter table public.event_status_history alter column changed_by drop not null;
