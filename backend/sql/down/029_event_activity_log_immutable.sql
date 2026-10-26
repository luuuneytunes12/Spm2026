-- Undo sql/029_event_activity_log_immutable.sql.
drop trigger if exists event_status_history_immutable on public.event_status_history;
drop function if exists public.refuse_event_activity_mutation();
update public.event_status_history history
set changed_by = events.organiser_id
from public.events
where history.event_id = events.id
  and history.changed_by is null;
alter table public.event_status_history
    alter column changed_by set not null;
alter table public.event_status_history drop column if exists actor_name;
