-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Filter Venues by Date and Time: a venue is free for an event only when
-- nothing clashes with it once the venue's setup and turnaround time are
-- counted, and a tentative hold counts as taking the venue.
--
--   * venues.setup_minutes / venues.turnaround_minutes -- time kept free
--     before every event (preparation) and after it (reset). Default 0, so
--     existing venues behave exactly as before until Venue Staff set them.
--
--   * booking_status 'hold_expired' -- a tentative hold (a 'pending'
--     request) that lapsed before it was confirmed. Like 'rejected' and
--     'cancelled', it no longer holds the venue.
--
-- Mirrored in db/schema.sql.
--
-- Rollback (Postgres cannot drop one value from an enum, so the type is
-- rebuilt without it; any hold_expired row becomes cancelled first):
--
--   alter table public.venues
--       drop column if exists setup_minutes,
--       drop column if exists turnaround_minutes;
--   update public.venue_bookings set status = 'cancelled' where status = 'hold_expired';
--   drop index if exists public.uq_venue_bookings_one_live_per_event;
--   alter table public.venue_bookings alter column status drop default;
--   alter type public.booking_status rename to booking_status_old;
--   create type public.booking_status as enum ('pending', 'approved', 'rejected', 'cancelled');
--   alter table public.venue_bookings
--       alter column status type public.booking_status using status::text::public.booking_status,
--       alter column status set default 'pending';
--   drop type public.booking_status_old;
--   create unique index uq_venue_bookings_one_live_per_event
--       on public.venue_bookings (event_id) where status in ('pending', 'approved');

alter table public.venues
    add column if not exists setup_minutes integer not null default 0,
    add column if not exists turnaround_minutes integer not null default 0;

do $$
begin
    alter table public.venues
        add constraint venues_setup_minutes_check check (setup_minutes >= 0);
exception when duplicate_object then null;
end $$;

do $$
begin
    alter table public.venues
        add constraint venues_turnaround_minutes_check check (turnaround_minutes >= 0);
exception when duplicate_object then null;
end $$;

alter type public.booking_status add value if not exists 'hold_expired';
