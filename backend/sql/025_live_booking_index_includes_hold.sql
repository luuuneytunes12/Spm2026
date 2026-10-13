-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- A pending request that is put on a tentative hold keeps its row, so the
-- "one live booking per event and venue" index must count 'tentative_hold' as
-- live too. Otherwise the same event could file a second request for a venue
-- it already holds. Needs sql/019_multi_venue_tentative_holds.sql applied
-- first (it adds the 'tentative_hold' value).
-- Rollback: sql/down/025_live_booking_index_includes_hold.sql

drop index if exists public.uq_venue_bookings_one_live_per_event_venue;

create unique index uq_venue_bookings_one_live_per_event_venue
    on public.venue_bookings (event_id, venue_id)
    where status in ('pending', 'tentative_hold', 'approved');
