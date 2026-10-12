-- Week 7: events may use multiple venues, and tentative holds have a deadline.
-- Booking history remains in venue_bookings; only the one-live-row restriction
-- is removed. Expired holds are transitioned to cancelled by application work.

alter type booking_status add value if not exists 'tentative_hold';
alter table venue_bookings add column if not exists expires_at timestamptz;
drop index if exists uq_venue_bookings_one_live_per_event;
