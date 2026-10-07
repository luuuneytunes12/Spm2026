-- Undo sql/019_venue_bookings_many_per_event.sql.
--
-- The old rule allowed ONE live booking per event, so when an event holds
-- several the oldest stays and the rest are cancelled (never deleted: the
-- history of what was asked stays). The per-venue needs columns are dropped.

update public.venue_bookings b
set status = 'cancelled'
where b.status in ('pending', 'approved')
  and exists (
      select 1 from public.venue_bookings older
      where older.event_id = b.event_id
        and older.status in ('pending', 'approved')
        and older.id < b.id
  );

drop index if exists public.uq_venue_bookings_one_live_per_event_venue;

create unique index if not exists uq_venue_bookings_one_live_per_event
    on public.venue_bookings (event_id)
    where status in ('pending', 'approved');

alter table public.venue_bookings
    drop column if exists room_layout_preference,
    drop column if exists accessibility_needs,
    drop column if exists facilities_needs;
