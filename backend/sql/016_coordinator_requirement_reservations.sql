-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Supports "Update Equipment Requirement Status" (Technical Support):
--
--   As a Technical Support Staff member, I want to update the status of an
--   event's equipment requirements, so that the Event Coordinator can track
--   progress.
--
-- Technical Support reserves equipment for a requirement through the
-- EXISTING reservation (Equipment Reservations): an equipment_requests row
-- moved to 'reserved'. This table records which reserved item is fulfilling
-- which Coordinator requirement. It adds nothing to equipment_requests and
-- changes nothing about how a reservation is made or counted.
--
-- Why it is keyed by (event, item), not by the reservation row's id
-- ------------------------------------------------------------------
--   * The reservation row's id does not exist until the reservation is made.
--     A link to it could only be written AFTER the reservation's commit,
--     leaving a window where a reservation exists with no link. Keyed by
--     (event, item) the link is written in the same commit.
--   * An approved Organiser change deletes and rebuilds the event's
--     equipment_requests rows. A foreign key to a row would die with it; a
--     link to the item survives, and simply has no reservation behind it
--     until the item is reserved again.
--
-- How much a requirement has reserved is never stored. It is read from the
-- reserved equipment_requests rows these links point at, so there is no
-- second copy to go out of step. "Reserved" is likewise not a stored status
-- of a requirement; it is what the reservations add up to.
--
-- unique (event_id, equipment_id): (event, item) is already unique in
-- equipment_requests, so one reserved row can fulfil only one requirement.
-- event_id repeats the requirement's event so that can be enforced here.

create table if not exists public.coordinator_requirement_reservations (
    id bigint generated always as identity primary key,
    requirement_id bigint not null
        references public.coordinator_equipment_requirements (id) on delete cascade,
    event_id bigint not null references public.events (id) on delete cascade,
    equipment_id bigint not null references public.equipment (id) on delete restrict,
    created_at timestamptz not null default now(),
    constraint coordinator_requirement_reservations_event_item_key
        unique (event_id, equipment_id)
);

-- Everything reads a requirement's links by the requirement, and deleting a
-- requirement (ON DELETE CASCADE above) finds them the same way.
create index if not exists idx_coordinator_requirement_reservations_requirement
    on public.coordinator_requirement_reservations (requirement_id);

-- Verify:
select column_name, data_type, is_nullable
from information_schema.columns
where table_schema = 'public' and table_name = 'coordinator_requirement_reservations'
order by ordinal_position;
