-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- PART 1 fixes a broken trigger; PART 2 assigns roles.
-- Part 1 must run first or every UPDATE on public.users fails.

-- ---------------------------------------------------------------------
-- PART 1: drop an orphaned trigger.
--
-- `trg_users_updated_at` runs `set_updated_at()` BEFORE UPDATE on
-- public.users, which assigns NEW.updated_at -- but public.users has no
-- updated_at column, so EVERY update to the table errors with:
--     42703: record "new" has no field "updated_at"
--
-- The trigger came from an earlier migration written against a different
-- assumed shape of this table; the table was later (re)created without
-- updated_at, leaving the trigger behind. Nothing else uses it: `users`
-- is the only table with this trigger, and `events` is the only table
-- that actually has an updated_at column.
--
-- The set_updated_at() function itself is left in place -- it is harmless,
-- and is worth keeping if you later add updated_at to a table and want to
-- attach it there.
-- ---------------------------------------------------------------------

drop trigger if exists trg_users_updated_at on public.users;

-- ---------------------------------------------------------------------
-- PART 2: assign roles to the seeded test accounts.
-- Roles inferred from each account's email address.
-- admin@cs.local is deliberately left untouched.
-- ---------------------------------------------------------------------

update public.users set role = 'organiser'    where email = 'event_org@cs.local';
update public.users set role = 'coordinator'  where email = 'event_coord@cs.local';
update public.users set role = 'venue_staff'  where email = 'ven_staff@cs.local';
update public.users set role = 'tech_support' where email = 'tech_supp@cs.local';
update public.users set role = 'attendee'     where email = 'attend@cs.local';

-- Verify:
select id, name, email, role from public.users order by id;
