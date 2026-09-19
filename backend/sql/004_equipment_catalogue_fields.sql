-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Supports the "View Equipment Catalogue" story.
--
-- The Week 1 briefing describes the catalogue as holding "type, description,
-- quantity, location, and operational status". The table only had type
-- (category) and quantity, so this adds the missing three.

-- ---------------------------------------------------------------------
-- PART 1: operational status.
--
-- A SEPARATE type from the existing `equipment_status`. That one
-- ('requested','reviewing','reserved','rejected','cancelled') is the
-- lifecycle of an equipment REQUEST on equipment_requests -- it says
-- nothing about the condition of the physical item. Reusing it would
-- conflate "this request is reserved" with "this projector works", which
-- are different facts about different things.
--
-- Values follow the briefing: equipment may be "damaged, being repaired,
-- or otherwise unavailable". `retired` covers written-off items that
-- should stay in the catalogue for historical reservations but never be
-- offered again.
--
-- Postgres has no CREATE TYPE IF NOT EXISTS, hence the DO block.
-- ---------------------------------------------------------------------

do $$
begin
    if not exists (select 1 from pg_type where typname = 'equipment_operational_status') then
        create type equipment_operational_status as enum (
            'available', 'maintenance', 'damaged', 'retired'
        );
    end if;
end $$;

-- ---------------------------------------------------------------------
-- PART 2: the catalogue fields.
--
-- `description` is what the item IS, in plain language, for a Technical
-- Support Staff member scanning the list. It is not `technical_specs`,
-- which already exists and holds model numbers, wattage, connector types
-- and the like -- the briefing lists description separately.
--
-- `location` is where the item is physically stored. The briefing notes
-- equipment may be "located at another venue", which is a reason it might
-- not be usable for a given event.
--
-- `operational_status` defaults to 'available' and is NOT NULL: every item
-- has a condition, and an unknown one would silently drop out of
-- availability checks. Postgres 11+ stores the default in the catalog
-- rather than rewriting the table, so this is cheap even on a large table.
-- ---------------------------------------------------------------------

alter table public.equipment add column if not exists description text;
alter table public.equipment add column if not exists location text;
alter table public.equipment
    add column if not exists operational_status equipment_operational_status
    not null default 'available';

-- ---------------------------------------------------------------------
-- PART 3: index for "filter the catalogue by equipment type".
--
-- Cheap now, and the briefing asks the system to scale with the catalogue
-- over three years. Plain btree: `category` is filtered by equality, not
-- by pattern, so trigram/GIN would be overkill here.
-- ---------------------------------------------------------------------

create index if not exists idx_equipment_category on public.equipment (category);

-- Verify:
select column_name, data_type, udt_name, is_nullable, column_default
from information_schema.columns
where table_schema = 'public' and table_name = 'equipment'
order by ordinal_position;
