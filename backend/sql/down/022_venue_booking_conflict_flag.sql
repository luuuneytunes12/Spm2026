-- Undo sql/022_venue_booking_conflict_flag.sql. Which bookings were flagged
-- is lost; the Activity Log rows stay (they are ordinary history rows).

drop index if exists public.idx_venue_bookings_conflict_flagged;
alter table public.venue_bookings drop column if exists conflict_flagged_at;
