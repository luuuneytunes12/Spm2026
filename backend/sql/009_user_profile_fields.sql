-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Supports the "Edit User Profile" story: lets a registered user update
-- their own name, organisation, contact details, and communication
-- preference.
--
-- `communication_preference` is a small, fixed list (unlike event_type,
-- which the customer briefing explicitly leaves open-ended), so a native
-- enum is used here, same reasoning as user_role. `create type` has no
-- `if not exists` form, hence the guard below.

do $$
begin
    if not exists (select 1 from pg_type where typname = 'communication_preference') then
        create type communication_preference as enum ('email', 'sms', 'phone_call');
    end if;
end
$$;

alter table public.users add column if not exists organisation        text;
alter table public.users add column if not exists phone_country_code  text;
alter table public.users add column if not exists phone_number        text;
alter table public.users add column if not exists communication_preference communication_preference;

-- Verify:
select column_name, data_type, is_nullable
from information_schema.columns
where table_schema = 'public' and table_name = 'users'
order by ordinal_position;
