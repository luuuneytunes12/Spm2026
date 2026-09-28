-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Supports structured equipment line-items on an event request: the
-- Organiser picks a catalogue item and a quantity instead of typing
-- "2 projectors, 4 radio mics" into a free-text box.
--
-- One line per equipment item, per event. Quantity is how you ask for more
-- of something, so two lines naming the same item is always a mistake --
-- either a double-click or a misunderstanding of the form. Without this
-- constraint the two lines would also have to be summed everywhere
-- availability is calculated, which is a silent trap for whoever writes
-- the reservation story.
--
-- The API rejects duplicates with a 422 before reaching the database. This
-- constraint is the backstop for anything that writes to the table without
-- going through it (a migration, a fix-up script, a future endpoint).
--
-- Trade-off worth knowing: this also prevents a cancelled line and a fresh
-- request for the same item coexisting on one event. The table is empty
-- today and the reservation workflow does not exist yet, so this is
-- acceptable; revisit if that workflow needs to keep rejected lines as
-- history alongside a replacement.
--
-- Postgres has no ADD CONSTRAINT IF NOT EXISTS, hence the DO block.

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'equipment_requests_event_equipment_key'
    ) then
        alter table public.equipment_requests
            add constraint equipment_requests_event_equipment_key
            unique (event_id, equipment_id);
    end if;
end $$;

-- Verify:
select conname, pg_get_constraintdef(oid)
from pg_constraint
where conrelid = 'public.equipment_requests'::regclass
order by conname;
