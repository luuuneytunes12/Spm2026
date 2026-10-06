-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Operational Safety Check stories (Safety Officer):
--   * events gain an 'awaiting_safety_check' status between planning and
--     confirmed. 'confirmed' is "Safety Check Passed (Event Confirmed)".
--   * venues record their emergency access and known restrictions, and an
--     equipment line where it is placed, for the Safety Officer to read.
--   * a Safety Officer who requests changes or rejects flags the affected
--     booking / equipment line with a reason. The booking stays approved and
--     the line stays reserved, so neither releases its hold; staff clear the
--     flag by re-approving / re-confirming. Null means nothing outstanding.
--
-- Rollback:
--   alter table public.equipment_requests drop column if exists safety_recheck_reason;
--   alter table public.equipment_requests drop column if exists placement_notes;
--   alter table public.venue_bookings drop column if exists safety_recheck_reason;
--   alter table public.venues drop column if exists known_restrictions;
--   alter table public.venues drop column if exists emergency_access;
--   -- Postgres cannot drop an enum label; recreate the type without it:
--   update public.events set status = 'planning' where status = 'awaiting_safety_check';
--   alter type public.event_status rename to event_status_old;
--   create type public.event_status as enum (
--       'draft', 'submitted', 'under_review', 'changes_requested',
--       'approved', 'rejected', 'planning', 'confirmed', 'completed', 'cancelled'
--   );
--   alter table public.events alter column status drop default;
--   alter table public.events
--       alter column status type public.event_status using status::text::public.event_status;
--   alter table public.events alter column status set default 'draft';
--   drop type public.event_status_old;

alter type public.event_status add value if not exists 'awaiting_safety_check' after 'planning';

alter table public.venues
    add column if not exists emergency_access text,
    add column if not exists known_restrictions text;

alter table public.venue_bookings
    add column if not exists safety_recheck_reason text;

alter table public.equipment_requests
    add column if not exists placement_notes text,
    add column if not exists safety_recheck_reason text;
