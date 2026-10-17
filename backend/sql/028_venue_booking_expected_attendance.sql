-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Allow each venue booking to carry its own attendance for independent
-- suitability checks. NULL preserves backward compatibility by using the
-- Event's expected attendance.
-- Rollback: sql/down/028_venue_booking_expected_attendance.sql

alter table public.venue_bookings
    add column if not exists expected_attendance integer;

alter table public.venue_bookings
    drop constraint if exists ck_venue_booking_expected_attendance_positive;
alter table public.venue_bookings
    add constraint ck_venue_booking_expected_attendance_positive
    check (expected_attendance is null or expected_attendance > 0);
