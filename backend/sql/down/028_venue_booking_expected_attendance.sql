alter table public.venue_bookings
    drop constraint if exists ck_venue_booking_expected_attendance_positive;
alter table public.venue_bookings
    drop column if exists expected_attendance;
