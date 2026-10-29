-- Event workflow stories: Edit Event Details During Planning, and the
-- append-only Event Activity Log. Safe to re-run (idempotent).
-- backend/db/schema.sql carries the same change.

-- The Event's own contact details, independent of its Organiser account.
alter table public.events
    add column if not exists event_contact_name text,
    add column if not exists event_contact_email text;

-- A name for an actor that is not a user, e.g. "System" for the hold-expiry
-- sweeper. Ordinary entries resolve the actor through changed_by.
alter table public.event_status_history
    add column if not exists actor_name text;

-- An Activity Log entry is never edited or removed on its own. It may go only
-- together with its Event (ON DELETE CASCADE from events), which is how the
-- e2e cleanup removes test data.
create or replace function public.refuse_event_activity_mutation()
returns trigger
language plpgsql
as $$
begin
    if tg_op = 'DELETE'
       and not exists (select 1 from public.events where id = old.event_id) then
        return old;
    end if;
    raise exception 'Event activity log entries are immutable';
end;
$$;

drop trigger if exists event_status_history_immutable on public.event_status_history;
create trigger event_status_history_immutable
    before update or delete on public.event_status_history
    for each row execute function public.refuse_event_activity_mutation();

-- Rollback (run by hand, before rolling back any earlier migration that
-- edits event_status_history, e.g. sql/down/033):
--
--   drop trigger if exists event_status_history_immutable on public.event_status_history;
--   drop function if exists public.refuse_event_activity_mutation();
--   alter table public.event_status_history drop column if exists actor_name;
--   alter table public.events
--       drop column if exists event_contact_email,
--       drop column if exists event_contact_name;
