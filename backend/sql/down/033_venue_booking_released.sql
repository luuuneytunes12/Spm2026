-- Undo sql/033_venue_booking_released.sql.
--
-- Postgres cannot drop one value from an enum, so the type is rebuilt
-- without 'released'. Released bookings go back to 'cancelled' (their note
-- still says why), and System entries are attributed to the Event's
-- Organiser. Run as one transaction.

begin;

update public.venue_bookings set status = 'cancelled' where status = 'released';

update public.event_status_history h
   set changed_by = e.organiser_id
  from public.events e
 where h.event_id = e.id and h.changed_by is null;
alter table public.event_status_history alter column changed_by set not null;

-- Everything that compares status to a literal is dropped and re-made
-- against the rebuilt type.
drop index if exists public.uq_venue_bookings_one_live_per_event_venue;
alter table public.venue_bookings drop constraint if exists ck_venue_booking_hold_requires_expiry;
alter table public.venue_bookings drop constraint if exists venue_bookings_check1;
alter table public.venue_bookings alter column status drop default;

alter type public.booking_status rename to booking_status_033;
create type public.booking_status as enum (
    'pending', 'tentative_hold', 'approved', 'rejected', 'cancelled', 'hold_expired', 'replaced'
);
alter table public.venue_bookings
    alter column status type public.booking_status using status::text::public.booking_status;
drop type public.booking_status_033;

alter table public.venue_bookings alter column status set default 'pending';
alter table public.venue_bookings
    add constraint ck_venue_booking_hold_requires_expiry
    check (status <> 'tentative_hold' or expires_at is not null);
create unique index uq_venue_bookings_one_live_per_event_venue
    on public.venue_bookings (event_id, venue_id)
    where status in ('pending', 'tentative_hold', 'approved');

commit;
