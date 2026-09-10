-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Supports the "Draft an Event Request" / "Submit an Event Request" stories.
--
-- PART 1 lets an INCOMPLETE request be saved as a draft.
-- PART 2 adds four fields the event-request form collects.

-- ---------------------------------------------------------------------
-- PART 1: relax NOT NULL on the fields an Organiser may not have decided
-- yet when they first save.
--
-- A draft is by definition incomplete: the Organiser opens the form,
-- types a purpose, and saves before choosing a date. With these columns
-- NOT NULL that INSERT fails, so a draft could never be stored.
--
-- Completeness is NOT abandoned -- it moves to where the user story
-- actually wants it. POST /events/{id}/submit validates that every
-- mandatory field is present and returns the list of missing ones, so
-- the UI can flag them. The database enforces shape; the submit
-- endpoint enforces readiness.
--
-- The two existing CHECK constraints are unaffected and are deliberately
-- left in place: postgres passes a CHECK that evaluates to TRUE *or*
-- NULL, so `expected_attendance > 0` and `proposed_end > proposed_start`
-- still reject bad values while allowing an unset one.
-- ---------------------------------------------------------------------

alter table public.events alter column name                drop not null;
alter table public.events alter column proposed_start      drop not null;
alter table public.events alter column proposed_end        drop not null;
alter table public.events alter column expected_attendance drop not null;

-- ---------------------------------------------------------------------
-- PART 2: fields collected by the event-request form that the original
-- schema did not carry.
--
-- All nullable -- they are optional at draft time, and `event_type` is
-- the only one of the four that submit treats as mandatory.
--
-- `event_type` is plain text rather than an enum: the customer briefing
-- lists categories as open-ended ("...or any other type defined by
-- ConnectSphere"), and a native enum needs an ALTER TYPE migration for
-- every new value. Revisit if the customer fixes the list.
--
-- `room_layout_preference` is the *requested* layout, and is the event
-- side of venues.supported_layouts -- venue suitability checking later
-- compares the two.
-- ---------------------------------------------------------------------

alter table public.events add column if not exists event_type             text;
alter table public.events add column if not exists programme              text;
alter table public.events add column if not exists room_layout_preference text;
alter table public.events add column if not exists special_arrangements   text;

-- Verify:
select column_name, data_type, is_nullable
from information_schema.columns
where table_schema = 'public' and table_name = 'events'
order by ordinal_position;
