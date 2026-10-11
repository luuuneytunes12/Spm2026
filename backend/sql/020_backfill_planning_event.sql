-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Submit Venue Booking Request (SCRUM-39 AC3): the first venue booking moves an
-- 'Event Approved' event to 'Planning Event'. Bookings requested BEFORE that
-- rule existed left their events at 'Event Approved'; this moves them on, once,
-- and logs it in the Activity Log (attributed to the event's Coordinator, who
-- made the booking) so the history explains the change.
--
-- Only events that still hold a live (pending or approved) booking move: an
-- event whose bookings were all rejected or cancelled stays 'Event Approved'.
--
-- Rollback: sql/down/020_backfill_planning_event.sql

with moved as (
    update public.events e
    set status = 'planning_event'
    where e.status = 'event_approved'
      and e.coordinator_id is not null
      and exists (
          select 1 from public.venue_bookings b
          where b.event_id = e.id and b.status in ('pending', 'approved')
      )
    returning e.id, e.coordinator_id
)
insert into public.event_status_history (event_id, changed_by, from_status, to_status, note)
select id, coordinator_id, 'event_approved', 'planning_event',
       'Moved to Planning Event: a venue booking had already been requested (backfill).'
from moved;
