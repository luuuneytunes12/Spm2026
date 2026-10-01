-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Submit Venue Booking Request: an event may have only ONE live (pending or
-- approved) venue booking request. A rejected or cancelled one is history,
-- so the Coordinator can ask another venue.
--
-- The API checks this under a row lock on the event; this index is the
-- backstop for anything that writes without going through it.
--
-- Rollback: drop index if exists public.uq_venue_bookings_one_live_per_event;

create unique index if not exists uq_venue_bookings_one_live_per_event
    on public.venue_bookings (event_id)
    where status in ('pending', 'approved');
