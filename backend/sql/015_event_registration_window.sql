-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Open Registration for a Confirmed Event: the Coordinator enables
-- registration on a confirmed event and sets the dates between which
-- Attendees may register. Both are nullable -- null means "no window set".
--
-- Rollback:
--   alter table public.events drop constraint if exists events_registration_window_check;
--   alter table public.events drop column if exists registration_opens_at;
--   alter table public.events drop column if exists registration_closes_at;

alter table public.events
    add column if not exists registration_opens_at timestamptz,
    add column if not exists registration_closes_at timestamptz;

do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'events_registration_window_check'
    ) then
        alter table public.events
            add constraint events_registration_window_check
            check (registration_closes_at >= registration_opens_at);
    end if;
end $$;
