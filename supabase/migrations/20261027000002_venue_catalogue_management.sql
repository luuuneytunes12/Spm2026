-- From backend/sql/030_venue_catalogue_management.sql. Safe to re-run: staging had part of this
-- applied by hand before the pipeline existed.

-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- SCRUM-108 Manage Venue Catalogue Details:
--  * venue_activity: append-only log of venues added / edited (who, when)
--  * venue_bookings.review_flagged_at / review_reason: bookings kept but
--    flagged after a capacity reduction or a removed room layout
--  * venue names are unique ignoring case. Existing clashing names are
--    renamed first (the lowest id keeps its name; the others get " (id N)"
--    appended) so the unique index can always be built
-- Rollback: sql/down/030_venue_catalogue_management.sql

create table if not exists public.venue_activity (
    id bigint generated always as identity primary key,
    venue_id bigint not null references public.venues (id) on delete cascade,
    changed_by bigint references public.users (id) on delete set null,
    note text not null,
    created_at timestamptz not null default now()
);
create index if not exists idx_venue_activity_venue on public.venue_activity (venue_id, created_at desc);

alter table public.venue_bookings add column if not exists review_flagged_at timestamptz;
alter table public.venue_bookings add column if not exists review_reason text;

update public.venues v
set name = v.name || ' (id ' || v.id || ')'
where exists (
    select 1 from public.venues o
    where lower(o.name) = lower(v.name) and o.id < v.id
);

create unique index if not exists uq_venues_name_lower on public.venues (lower(name));
