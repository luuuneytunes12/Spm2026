-- Undo sql/020_backfill_planning_event.sql: put back only the events that
-- migration moved (found by its Activity Log note), and remove that note.

update public.events e
set status = 'event_approved'
where e.status = 'planning_event'
  and exists (
      select 1 from public.event_status_history h
      where h.event_id = e.id
        and h.note = 'Moved to Planning Event: a venue booking had already been requested (backfill).'
  );

delete from public.event_status_history
where note = 'Moved to Planning Event: a venue booking had already been requested (backfill).';