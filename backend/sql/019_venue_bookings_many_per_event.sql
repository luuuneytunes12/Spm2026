-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Submit Venue Booking Request (SCRUM-39): a Coordinator may ask for several
-- venues at once, so an event can now hold several live (pending or approved)
-- venue bookings -- one per venue. What stays true is that the SAME venue
-- cannot be live twice for one event: that is a double click, not a plan.
--
-- Each booking also carries the needs the Coordinator entered FOR THAT VENUE
-- (room layout, accessibility, facilities), so Venue Staff read what was asked
-- of their venue and not just what the Event says in general. Null means
-- "as the Event says"; existing rows are left null.
--
-- Supersedes sql/013_venue_bookings_one_live_per_event.sql.
-- Rollback: sql/down/019_venue_bookings_many_per_event.sql

drop index if exists public.uq_venue_bookings_one_live_per_event;

create unique index if not exists uq_venue_bookings_one_live_per_event_venue
    on public.venue_bookings (event_id, venue_id)
    where status in ('pending', 'approved');

alter table public.venue_bookings
    add column if not exists room_layout_preference text,
    add column if not exists accessibility_needs text,
    add column if not exists facilities_needs text;
