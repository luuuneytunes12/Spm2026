-- Undo sql/027_venue_hold_expired_status.sql.
--
-- Postgres cannot drop one value from an enum, so the type is rebuilt
-- without 'hold_expired'. Expired holds go back to 'cancelled' (their note
-- still says "Tentative hold expired."). Run as one transaction.

begin;

update public.venue_bookings set status = 'cancelled' where status = 'hold_expired';

alter table public.venue_bookings drop column if exists hold_reminder_sent_at;

-- Everything that compares status to a literal is dropped and re-made
-- against the rebuilt type.
drop index if exists public.uq_venue_bookings_one_live_per_event_venue;
alter table public.venue_bookings drop constraint if exists ck_venue_booking_hold_requires_expiry;
alter table public.venue_bookings drop constraint if exists venue_bookings_check1;
alter table public.venue_bookings alter column status drop default;

alter type public.booking_status rename to booking_status_027;
create type public.booking_status as enum ('pending', 'tentative_hold', 'approved', 'rejected', 'cancelled');
alter table public.venue_bookings
    alter column status type public.booking_status using status::text::public.booking_status;
drop type public.booking_status_027;

alter table public.venue_bookings alter column status set default 'pending';
alter table public.venue_bookings
    add constraint ck_venue_booking_hold_requires_expiry
    check (status <> 'tentative_hold' or expires_at is not null);
create unique index uq_venue_bookings_one_live_per_event_venue
    on public.venue_bookings (event_id, venue_id)
    where status in ('pending', 'tentative_hold', 'approved');

commit;
