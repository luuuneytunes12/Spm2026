-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- SCRUM-95: a replacement venue request records which booking it replaces,
-- and the original becomes 'replaced' (kept as history) once the replacement
-- is approved.
-- Rollback: sql/down/029_venue_booking_replacement.sql

alter type public.booking_status add value if not exists 'replaced';

alter table public.venue_bookings
    add column if not exists replaces_booking_id bigint
    references public.venue_bookings (id) on delete set null;
