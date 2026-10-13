-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Mark Venue Temporarily Unavailable (SCRUM-93): Venue Staff record a period
-- with a reason category (Maintenance, Equipment failure, Renovation, Safety
-- concern, Other). The existing `reason` text stays as optional details. Who
-- last edited or ended a period, and when, is kept in updated_by/updated_at.
-- Rows made before this get the category 'Other'.
--
-- Rollback: sql/down/023_venue_unavailability_reason.sql

alter table public.venue_unavailability
    add column if not exists reason_category text,
    add column if not exists updated_by bigint references public.users (id) on delete set null,
    add column if not exists updated_at timestamptz;

update public.venue_unavailability set reason_category = 'Other' where reason_category is null;

alter table public.venue_unavailability alter column reason_category set default 'Other';
alter table public.venue_unavailability alter column reason_category set not null;

alter table public.venue_unavailability
    drop constraint if exists venue_unavailability_reason_category_check;
alter table public.venue_unavailability
    add constraint venue_unavailability_reason_category_check
    check (reason_category in ('Maintenance', 'Equipment failure', 'Renovation', 'Safety concern', 'Other'));
