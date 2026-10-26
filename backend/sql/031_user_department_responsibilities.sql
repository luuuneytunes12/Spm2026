-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Supports "Record Department & Responsibilities" (SCRUM-19): internal staff
-- record the department they belong to (a fixed list) and a free-text
-- description of their responsibilities on their own profile.
--
-- Nullable: every existing row predates them, and Organisers / Attendees
-- never set them. The API requires a department from internal staff.

do $$
begin
    if not exists (select 1 from pg_type where typname = 'department') then
        create type department as enum (
            'events_coordination', 'venue_operations', 'technical_support', 'safety_compliance'
        );
    end if;
end
$$;

alter table public.users add column if not exists department department;
alter table public.users add column if not exists responsibilities text;
