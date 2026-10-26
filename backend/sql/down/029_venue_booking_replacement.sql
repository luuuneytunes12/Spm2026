-- Postgres cannot drop an enum label: bookings already 'replaced' go back to
-- 'cancelled' and the label stays unused.
update public.venue_bookings set status = 'cancelled' where status = 'replaced';
alter table public.venue_bookings drop column if exists replaces_booking_id;
