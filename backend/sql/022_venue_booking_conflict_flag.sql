-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Flag Conflicting Bookings (SCRUM-92): when a venue's setup/turnaround is
-- saved, a future approved booking that now clashes with another approved
-- booking is FLAGGED, never cancelled. conflict_flagged_at is when it was
-- flagged; NULL means not flagged. The Activity Log line for a flag, an
-- automatic un-flag or a "keep with reason" is an event_status_history row
-- (from_status = to_status = the event's status, with a note), so no other
-- table changes.
--
-- Rollback: sql/down/022_venue_booking_conflict_flag.sql

alter table public.venue_bookings
    add column if not exists conflict_flagged_at timestamptz;

create index if not exists idx_venue_bookings_conflict_flagged
    on public.venue_bookings (start_time)
    where conflict_flagged_at is not null;
