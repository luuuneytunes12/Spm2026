-- Undo sql/024_booking_status_hold.sql.
-- Postgres cannot drop a value from an enum. Rows still using 'hold' must be
-- moved to another status first; the unused label can safely stay.
update public.venue_bookings set status = 'cancelled' where status = 'hold';
