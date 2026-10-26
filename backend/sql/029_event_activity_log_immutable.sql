-- Run in the Supabase SQL editor. Rollback: sql/down/029_event_activity_log_immutable.sql
--
-- `actor_name` is reserved for non-user actors (for example, the hold
-- expiry sweeper); ordinary entries resolve the actor through changed_by.
alter table public.event_status_history
    add column if not exists actor_name text;
alter table public.event_status_history
    alter column changed_by drop not null;

create or replace function public.refuse_event_activity_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'Event activity log entries are immutable';
end;
$$;

drop trigger if exists event_status_history_immutable on public.event_status_history;
create trigger event_status_history_immutable
    before update or delete on public.event_status_history
    for each row execute function public.refuse_event_activity_mutation();
