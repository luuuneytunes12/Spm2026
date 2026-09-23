-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Supports AC5 of "Mark myself unavailable": every toggle of a
-- Coordinator's own availability must be logged with a timestamp, even
-- when they have zero active events at the time -- in which case nothing
-- gets written to event_status_history, since that table requires an
-- event_id and only ever gets a row as a side effect of reassigning one.

create table if not exists public.coordinator_availability_history (
    id bigint generated always as identity primary key,
    coordinator_id bigint not null references public.users (id) on delete cascade,
    is_available boolean not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_coordinator_availability_history_coordinator
    on public.coordinator_availability_history (coordinator_id, created_at desc);

-- Verify:
select * from public.coordinator_availability_history order by created_at desc limit 20;
