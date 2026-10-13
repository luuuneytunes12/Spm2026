-- Undo sql/025_live_booking_index_includes_hold.sql.
-- Fails if an event now has a pending request and a tentative hold on one venue.

drop index if exists public.uq_venue_bookings_one_live_per_event_venue;

create unique index uq_venue_bookings_one_live_per_event_venue
    on public.venue_bookings (event_id, venue_id)
    where status in ('pending', 'approved');
