-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Configure Venue Setup & Turnaround Time (SCRUM-78): Venue Staff record, per
-- venue, the whole minutes needed to set up before an Event and to reset
-- after it. NULL means "not set" (0 is used when working out availability).
-- Who saved them last, and when, is kept alongside.
--
-- Rollback: sql/down/021_venue_setup_turnaround.sql

alter table public.venues
    add column if not exists setup_minutes integer,
    add column if not exists turnaround_minutes integer,
    add column if not exists setup_turnaround_updated_by bigint
        references public.users (id) on delete set null,
    add column if not exists setup_turnaround_updated_at timestamptz;

alter table public.venues drop constraint if exists venues_setup_minutes_check;
alter table public.venues add constraint venues_setup_minutes_check
    check (setup_minutes is null or setup_minutes >= 0);

alter table public.venues drop constraint if exists venues_turnaround_minutes_check;
alter table public.venues add constraint venues_turnaround_minutes_check
    check (turnaround_minutes is null or turnaround_minutes >= 0);
