-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Supports "Record Equipment Requirements for Event" (Event Coordinator):
--
--   As an Event Coordinator, I want to record the equipment an event
--   requires, so that Technical Support Staff know what to review and
--   reserve.
--
-- A requirement is the Coordinator's own record of what an event needs:
-- an equipment TYPE (a catalogue category), a quantity, and technical
-- notes. It gets its own table rather than reusing equipment_requests.
--
-- Why a separate table
-- --------------------
-- equipment_requests holds the ORGANISER's picks. When an Organiser's
-- change request is approved, replace_equipment_lines deletes every row of
-- that table for the event and rebuilds it from the Organiser's list. A
-- Coordinator requirement stored there would be deleted along with them.
--
-- The link, and which side owns it
-- --------------------------------
-- organiser_equipment_request_id points FROM the requirement TO the
-- Organiser's pick it was based on. The Organiser's table is untouched and
-- knows nothing about requirements.
--
--   * One Organiser pick may have zero or many requirements; a requirement
--     refers to at most one pick.
--   * It is nullable: the Coordinator may record an operational need that
--     did not come from anything the Organiser asked for.
--   * ON DELETE SET NULL, not CASCADE: when the Organiser's pick is
--     deleted or replaced, the requirement survives and simply loses its
--     link.
--
-- status reuses the existing equipment_status enum. Every requirement is
-- 'requested' for now; moving it on is Technical Support's job, in a later
-- story.
--
-- Not enforced on purpose: one requirement per type, per event. Six
-- microphones and a PA system are both "Audio" and are separate needs.

create table if not exists public.coordinator_equipment_requirements (
    id bigint generated always as identity primary key,
    event_id bigint not null references public.events (id) on delete cascade,
    organiser_equipment_request_id bigint
        references public.equipment_requests (id) on delete set null,
    category text not null check (length(btrim(category)) > 0),
    quantity_needed integer not null check (quantity_needed > 0),
    technical_notes text,
    status equipment_status not null default 'requested',
    created_by bigint not null references public.users (id) on delete restrict,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- Everything reads a requirement by its event.
create index if not exists idx_coordinator_equipment_requirements_event
    on public.coordinator_equipment_requirements (event_id);

-- Backs the ON DELETE SET NULL above: without it, deleting an Organiser's
-- pick scans the whole table to find requirements that reference it.
-- Partial, because most requirements have no link and need no entry.
create index if not exists idx_coordinator_equipment_requirements_pick
    on public.coordinator_equipment_requirements (organiser_equipment_request_id)
    where organiser_equipment_request_id is not null;

-- Verify:
select column_name, data_type, is_nullable
from information_schema.columns
where table_schema = 'public' and table_name = 'coordinator_equipment_requirements'
order by ordinal_position;
