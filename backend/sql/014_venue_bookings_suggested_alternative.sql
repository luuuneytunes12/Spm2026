-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Approve or Reject Venue Booking Request: when Venue Staff reject a request
-- they may record a reason, an alternative, or both. The reason goes in the
-- existing `decision_notes`; this adds the column for the alternative
-- (another venue, another time), kept separate so the Coordinator is shown
-- "why not" and "what instead" as two distinct answers.
--
-- Rollback: alter table public.venue_bookings drop column if exists suggested_alternative;

alter table public.venue_bookings
    add column if not exists suggested_alternative text;
